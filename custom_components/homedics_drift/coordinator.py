"""Persistent Bluetooth session for one Drift table."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    close_stale_connections_by_address,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BACKOFF_MAX,
    BACKOFF_START,
    CONF_AI_TASK_ENTITY,
    CONF_CLEAN_BEFORE_AI,
    CONF_CONVERSATION_AGENT,
    DOMAIN,
    NOTIFY_UUID,
    POWER_DEBOUNCE,
    READY_TIMEOUT,
    WRITE_UUID,
)
from .drawing import (
    build_instructions,
    UploadTicks,
    choose_drawing_assistant,
    clean_before_ai_drawing,
    feedback_text,
    generated_thr,
    model_text,
    path_from_model,
)
from .gallery import gallery_names, gallery_thr, random_gallery
from .patterns import (
    STORAGE_CAP,
    PatternLibrary,
    CleanList,
    PatternRejected,
    allocate_id,
    choose_clean_upload_id,
    cleaning_spiral,
    clean_play_order,
    deletion_refusal,
    documents_from_download,
    find_stock_clean,
    https_pattern_url,
    inbox_names,
    reusable_id,
    label_patterns,
    paginate,
    path_under_config,
    resend_indexes,
    spiral_thr,
    thr_to_wire,
    wire_point,
)
from .preview import render_thr
from .protocol import (
    CMD_PLAYLIST_LIST,
    DriftState,
    Kind,
    LampHold,
    Message,
    PatternCatalogue,
    PlaylistCatalogue,
    alarm_text,
    brightness,
    delete_patterns,
    draw_pattern,
    draw_playlist,
    end_upload,
    fixed_color,
    lamp_on_packets,
    reconcile_lamp,
    next_pattern,
    pattern_page,
    play_pause,
    previous_pattern,
    session_actions,
    start_upload,
    reply_for,
    speed_raw,
    Packet,
    PacketParser,
    PowerQueue,
    percent_to_speed_raw,
    playback_allowed,
)

_LOGGER = logging.getLogger(__name__)

type DriftConfigEntry = ConfigEntry[DriftCoordinator]


class DriftCoordinator(DataUpdateCoordinator[DriftState]):
    """Hold one GATT session, answer the table, and publish its state.

    The table drops the session about two seconds after it stops hearing host
    frames, so the connection stays up and every notification is acknowledged.
    The link is closed on unload and on Home Assistant stop, which frees the
    table for the official phone app. A dropped or unplugged table marks the
    entities unavailable and is retried with backoff.
    """

    config_entry: DriftConfigEntry

    def __init__(self, hass: HomeAssistant, entry: DriftConfigEntry) -> None:
        """Set up a coordinator for a configured table."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=None,
        )
        self.data = None  # type: ignore[assignment]
        self.address = entry.data["address"]
        self.catalogue = PlaylistCatalogue()
        self.patterns = PatternCatalogue()
        self.lamp_brightness = 100
        self.lamp_color: tuple[int, int, int] = (255, 255, 255)
        self.lamp_color_name = "Temp"
        self._lamp_hold: LampHold | None = None
        # Owned by the integration. The table's powerOn byte does not write this.
        self.session_on = True
        self.session_settled = True
        self._session_restored = False
        self._off_enforced = False
        self._power_queue = PowerQueue()
        self._power_worker: asyncio.Task[None] | None = None
        self._command_lock = asyncio.Lock()
        self._notices: asyncio.Queue[Message] = asyncio.Queue()
        self.library = PatternLibrary()
        self._library_store = Store(hass, 1, f"{DOMAIN}_{self.address.replace(':', '')}_patterns")
        self.inbox: list[str] = []
        self.inbox_choice: str | None = None
        self.preview_at: datetime | None = None
        self._inbox_unsub: Any = None
        self._seen_pattern_id: int | None = None
        self._clean_follow = 0
        self.ai_prompt = ""
        self.ai_status = "idle"
        self.ai_error = ""
        self.ai_detail = ""
        self.ai_name = ""
        self.ai_pattern_id: int | None = None
        self.ai_progress: int | None = None
        self._draw_active = False
        self._upload_ticks = UploadTicks()
        self.gallery_choice = gallery_names()[0]
        self.gallery_preview_at: datetime | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._device: BLEDevice | None = None
        self._parser = PacketParser()
        self._out: asyncio.Queue[tuple[Packet, asyncio.Future[None] | None]] | None = None
        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._stopping = False
        self._shut_down = False
        self._task: asyncio.Task[None] | None = None
        self._last_alarm: tuple[int | None, tuple[int, ...]] | None = None
        self._unknown_playlists: set[str] = set()

    def start(self) -> None:
        """Start the background connection loop."""
        self._task = self.hass.async_create_background_task(
            self._run(),
            name=f"{DOMAIN}-{self.address}",
        )
        self._inbox_unsub = async_track_time_interval(
            self.hass, self._scan_inbox, timedelta(seconds=120)
        )
        self.hass.async_create_task(self._scan_inbox(None), name=f"{DOMAIN}-inbox-{self.address}")

    async def async_shutdown(self) -> None:
        """Cancel reconnects and drop the GATT connection."""
        if self._shut_down:
            return
        self._shut_down = True
        self._stopping = True
        self._disconnected.set()
        self._ready.set()
        task = self._task
        self._task = None
        power_worker = self._power_worker
        self._power_worker = None
        if self._inbox_unsub is not None:
            self._inbox_unsub()
            self._inbox_unsub = None
        for job in (task, power_worker):
            if job is not None and job is not asyncio.current_task() and not job.done():
                job.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await job
        await self._disconnect_client()
        await super().async_shutdown()

    async def _run(self) -> None:
        backoff = BACKOFF_START
        try:
            while not self._stopping:
                try:
                    await self._session()
                    backoff = BACKOFF_START
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # Bleak and link errors must not kill the loop.
                    _LOGGER.debug("Drift %s session ended: %s", self.address, err)
                    self.async_set_update_error(err)
                if self._stopping:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
        finally:
            await self._disconnect_client()

    async def _session(self) -> None:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise ConnectionError(
                f"{self.address} is not visible to a Bluetooth adapter or proxy"
            )
        self._device = device
        await close_stale_connections_by_address(self.address)
        self._parser = PacketParser()
        self._ready.clear()
        self._disconnected.clear()
        self._out = asyncio.Queue()
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.name,
            self._on_disconnect,
            max_attempts=4,
            ble_device_callback=self._fresh_device,
        )
        self._client = client
        writer = asyncio.create_task(self._writer(), name=f"{DOMAIN}-write-{self.address}")
        try:
            await client.start_notify(NOTIFY_UUID, self._on_notify)
            _LOGGER.info("Connected to Drift %s (%s)", self.name, self.address)
            await self._disconnected.wait()
            raise ConnectionError("Drift disconnected")
        finally:
            self._ready.clear()
            self._client = None
            writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await writer
            self._out = None
            with contextlib.suppress(Exception):
                if client.is_connected:
                    await client.stop_notify(NOTIFY_UUID)
            with contextlib.suppress(Exception):
                await client.disconnect()

    def _fresh_device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is not None:
            self._device = device
        if self._device is None:
            raise BleakError(f"{self.address} disappeared")
        return self._device

    def _on_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        self.hass.loop.call_soon_threadsafe(self._disconnected.set)

    def _on_notify(self, sender_or_data: Any, data: bytearray | None = None) -> None:
        payload = bytes(data if data is not None else sender_or_data)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.hass.loop:
            self._handle_bytes(payload)
        else:
            self.hass.loop.call_soon_threadsafe(self._handle_bytes, payload)

    def _handle_bytes(self, data: bytes) -> None:
        try:
            packets = self._parser.feed(data)
        except Exception:
            _LOGGER.exception("Drift notify bytes could not be parsed")
            return
        for packet in packets:
            try:
                self._handle_packet(packet)
            except Exception:
                _LOGGER.exception("Drift packet could not be handled")

    def _handle_packet(self, packet: Packet) -> None:
        reply = reply_for(packet)
        if reply is not None:
            self._enqueue(reply, None)
        message = self.catalogue.ingest(packet)
        patterns_changed = self.patterns.note(message)
        if message.kind is Kind.WAITING:
            self._ready.clear()
            self._off_enforced = False
            self._publish()
            return
        if message.kind is Kind.INIT_COMPLETE:
            if not self._ready.is_set():
                _LOGGER.info(
                    "Drift %s session ready (%s playlist(s), %s pattern(s))",
                    self.address,
                    len(self.catalogue.playlists),
                    len(self.patterns.pattern_ids),
                )
            self._ready.set()
            self._publish()
            self._enforce_saved_off()
            return
        if message.kind in (
            Kind.UPLOAD_MISSING,
            Kind.UPLOAD_STARTED,
            Kind.UPLOAD_STORED,
            Kind.UPLOAD_FAILED,
            Kind.DELETE_COMPLETE,
            Kind.NO_STORAGE,
        ):
            self._notices.put_nowait(message)
        if message.kind is Kind.STATE and message.state is not None:
            self._apply_lamp_report(message.state, message.state.brightness)
            if message.state.pattern_id != self._seen_pattern_id:
                self._seen_pattern_id = message.state.pattern_id
                self.preview_at = datetime.now(timezone.utc)
            self.async_set_updated_data(message.state)
            return
        if message.kind is Kind.LIGHT_MODE and message.light_brightness is not None:
            self._apply_light_mode(message)
            return
        if message.kind in (Kind.PLAYLIST, Kind.PLAYLIST_RESET) or patterns_changed:
            self._publish()
            return
        if message.kind is Kind.ALARM and message.alarm_codes is not None:
            signature = (message.alarm_kind, tuple(message.alarm_codes))
            if signature != self._last_alarm:
                self._last_alarm = signature
                _LOGGER.warning(
                    "Drift %s alarm: %s",
                    self.address,
                    alarm_text(message.alarm_codes),
                )
            return
        if message.kind is Kind.OTHER and packet.command == CMD_PLAYLIST_LIST:
            key = packet.data.hex()
            if key not in self._unknown_playlists:
                self._unknown_playlists.add(key)
                _LOGGER.debug("Unrecognized Drift playlist packet: %s", key)

    def _apply_lamp_report(self, state: DriftState, reported: int) -> None:
        """Publish lamp on/off without letting a stale status undo a command.

        While the power switch is off the lamp stays off in Home Assistant.
        A brightness the table still reports must not be remembered as the
        level to restore, and must not turn the lamp entity back on.
        """
        if not self.session_on:
            state.lamp_on = False
            return
        level, lamp_on, self._lamp_hold = reconcile_lamp(reported, self._lamp_hold)
        state.brightness = level
        state.lamp_on = lamp_on
        if self._lamp_hold is None and lamp_on and level > 0:
            self.lamp_brightness = level
            self.lamp_color = state.color
            if state.color_name:
                self.lamp_color_name = state.color_name

    def _remember_lamp(self) -> None:
        """Keep the lit colour and level before the power switch turns the lamp off."""
        state = self.data
        if state is None or not state.lamp_on or state.brightness <= 0:
            return
        self.lamp_brightness = state.brightness
        self.lamp_color = state.color
        if state.color_name:
            self.lamp_color_name = state.color_name

    def _apply_light_mode(self, message: Message) -> None:
        """Apply the table's ``0x31/4`` light-mode echo. Brightness 0 is off."""
        if self.data is None or message.light_brightness is None:
            return
        if message.light_shifting is not None:
            self.data.shifting = message.light_shifting
        if message.light_shift_time is not None:
            self.data.shift_time = message.light_shift_time
        if message.light_breathing is not None:
            self.data.breathing = message.light_breathing
        self._apply_lamp_report(self.data, message.light_brightness)
        self.async_set_updated_data(self.data)

    def _publish(self) -> None:
        if self.data is not None:
            self.async_update_listeners()

    def _enqueue(self, packet: Packet, future: asyncio.Future[None] | None) -> None:
        if self._out is None:
            if future is not None and not future.done():
                future.set_exception(HomeAssistantError("Drift table is not connected"))
            return
        self._out.put_nowait((packet, future))

    async def _writer(self) -> None:
        assert self._out is not None
        queue = self._out
        try:
            while True:
                packet, future = await queue.get()
                try:
                    client = self._client
                    if client is None or not client.is_connected:
                        raise ConnectionError("Drift is not connected")
                    await client.write_gatt_char(WRITE_UUID, packet.encode(), response=False)
                except Exception as err:
                    if future is not None and not future.done():
                        future.set_exception(err)
                    else:
                        _LOGGER.debug("Drift reply was not written: %s", err)
                else:
                    if future is not None and not future.done():
                        future.set_result(None)
        except asyncio.CancelledError:
            while not queue.empty():
                _packet, future = queue.get_nowait()
                if future is not None and not future.done():
                    future.set_exception(ConnectionError("Drift disconnected"))
            raise

    async def async_send(self, packet: Packet) -> None:
        """Send a user command once the handshake has finished."""
        if self._shut_down:
            raise HomeAssistantError("Drift table is not connected")
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), READY_TIMEOUT)
            except TimeoutError as err:
                raise HomeAssistantError(
                    "Drift table has not finished its handshake"
                ) from err
        if self._shut_down or self._client is None or self._out is None:
            raise HomeAssistantError("Drift table is not connected")
        future: asyncio.Future[None] = self.hass.loop.create_future()
        self._enqueue(packet, future)
        await future

    def _replace(self, **changes: Any) -> None:
        state = self.data
        if state is None:
            return
        for key, value in changes.items():
            setattr(state, key, value)
        self.async_set_updated_data(state)

    def adopt_session(self, on: bool) -> None:
        """Restore the switch from Home Assistant, without reading ``powerOn``."""
        self.session_on = bool(on)
        self._session_restored = True
        self.session_settled = True
        self._publish()
        self._enforce_saved_off()

    def _enforce_saved_off(self) -> None:
        """After connect, make a restored off switch pause and extinguish once."""
        if self._shut_down or not self._session_restored or self.session_on:
            return
        if not self._ready.is_set() or self._off_enforced:
            return
        self._off_enforced = True
        self._power_queue.push(False)
        self._ensure_power_worker()

    def _ensure_power_worker(self) -> None:
        worker = self._power_worker
        if worker is None or worker.done():
            self._power_worker = self.hass.async_create_task(
                self._drain_power(),
                name=f"{DOMAIN}-power-{self.address}",
            )

    async def async_set_power(self, on: bool) -> None:
        """Integration power. Off pauses and turns the lamp off. On restores both.

        The switch changes immediately and is not revised by status packets.
        Quick presses collapse to the last request and run one at a time.
        ``0x14/16`` is not sent.
        """
        requested = bool(on)
        if not requested:
            self._clean_follow += 1
            self._remember_lamp()
        self.session_on = requested
        self.session_settled = False
        self._power_queue.push(requested)
        self._publish()
        self._ensure_power_worker()

    async def _drain_power(self) -> None:
        """Run the latest pause/light or restore/resume sequence."""
        while not self._shut_down:
            try:
                await asyncio.sleep(POWER_DEBOUNCE)
                target = self._power_queue.pop()
                if target is None:
                    self.session_settled = True
                    self._publish()
                    return
                self.session_on = target
                self.session_settled = False
                self._publish()
                async with self._command_lock:
                    if target:
                        await self._session_on()
                    else:
                        await self._session_off()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.debug("Drift power change was not finished", exc_info=True)
                if self._power_queue.pending is None:
                    self.session_settled = True
                    self._publish()
                    return

    async def _session_off(self) -> None:
        """Pause a moving ball, then turn the lamp off. Leave ``powerOn`` alone."""
        drawing = bool(self.data and self.data.drawing)
        for action in session_actions(False, drawing=drawing):
            if action == "pause":
                await self.async_send(play_pause())
                self._replace(status=0)
            elif action == "light_off":
                await self._set_brightness(0)

    async def _session_on(self) -> None:
        """Restore the remembered lamp, then resume play if the ball is idle."""
        drawing = bool(self.data and self.data.drawing)
        for action in session_actions(True, drawing=drawing):
            if action == "light_on":
                await self._turn_lamp_on(max(1, self.lamp_brightness))
            elif action == "resume":
                if self.data is None or not self.data.drawing:
                    await self.async_send(play_pause())
                    self._replace(status=1)

    async def async_toggle_playback(self) -> None:
        """Send play/pause. This does not change the power switch."""
        async with self._command_lock:
            if not playback_allowed(self.session_on):
                return
            drawing = bool(self.data and self.data.drawing)
            await self.async_send(play_pause())
            self._replace(status=0 if drawing else 1)

    async def async_next(self) -> None:
        async with self._command_lock:
            if not playback_allowed(self.session_on):
                return
            await self.async_send(next_pattern())

    async def async_previous(self) -> None:
        async with self._command_lock:
            if not playback_allowed(self.session_on):
                return
            await self.async_send(previous_pattern())

    async def async_set_speed_percent(self, percent: float) -> None:
        async with self._command_lock:
            raw = percent_to_speed_raw(percent)
            await self.async_send(speed_raw(raw))
            self._replace(speed_raw=raw)

    async def async_set_brightness(self, level: int) -> None:
        """Dim with ``0x14/7``. Zero is what turns the ST-300 lamp off."""
        async with self._command_lock:
            await self._set_brightness(level)

    async def _set_brightness(self, level: int) -> None:
        level = max(0, min(100, int(level)))
        await self.async_send(brightness(level))
        if level > 0:
            self.lamp_brightness = level
            self._lamp_hold = LampHold(True, level)
            self._replace(brightness=level, lamp_on=True)
            return
        self._lamp_hold = LampHold(False, 0)
        self._replace(brightness=0, lamp_on=False)

    async def async_turn_lamp_on(self, level: int) -> None:
        """Turn the lamp on with ``0x11/4`` and, from off, the last colour."""
        async with self._command_lock:
            await self._turn_lamp_on(level)

    async def _turn_lamp_on(self, level: int) -> None:
        """Turn the lamp on with ``0x11/4`` and, from off, the last colour.

        The toggle is updated as soon as the write finishes. A status packet
        that still reports the old brightness does not undo that until the
        table echoes the new level.
        """
        level = max(1, min(100, int(level)))
        state = self.data
        from_off = state is None or not state.lamp_on
        for packet in lamp_on_packets(
            level=level,
            color=self.lamp_color,
            color_name=self.lamp_color_name,
            shifting=bool(state and state.shifting),
            shift_time=int(state.shift_time) if state else 0,
            breathing=bool(state and state.breathing),
            from_off=from_off,
        ):
            await self.async_send(packet)
        self.lamp_brightness = level
        self._lamp_hold = LampHold(True, level)
        if from_off and (not self.lamp_color_name or self.lamp_color_name == "Temp"):
            self._replace(
                brightness=level,
                lamp_on=True,
                color=self.lamp_color,
                color_name="Temp",
                shifting=False,
                breathing=False,
                shift_time=0,
            )
        elif from_off:
            self._replace(brightness=level, lamp_on=True, color_name=self.lamp_color_name)
        else:
            self._replace(brightness=level, lamp_on=True)

    async def async_set_color(self, rgb: tuple[int, int, int], level: int) -> None:
        """Store a fixed colour as palette entry Temp so it survives disconnect."""
        async with self._command_lock:
            await self._set_color(rgb, level)

    async def _set_color(self, rgb: tuple[int, int, int], level: int) -> None:
        level = max(1, min(100, int(level)))
        red, green, blue = (max(0, min(255, int(channel))) for channel in rgb)
        for packet in fixed_color(red, green, blue, level):
            await self.async_send(packet)
        self.lamp_brightness = level
        self.lamp_color = (red, green, blue)
        self.lamp_color_name = "Temp"
        self._lamp_hold = LampHold(True, level)
        self._replace(
            color=(red, green, blue),
            color_name="Temp",
            brightness=level,
            lamp_on=True,
            shifting=False,
            breathing=False,
            shift_time=0,
        )

    def _require_awake(self) -> None:
        """Refuse playback while the integration power switch is off."""
        if not playback_allowed(self.session_on):
            raise HomeAssistantError("Drift power is off")

    async def async_select_playlist(self, label: str) -> None:
        """Draw the playlist the table reported under ``label``."""
        async with self._command_lock:
            await self._select_playlist(label)

    async def _select_playlist(self, label: str) -> None:
        self._require_awake()
        playlist = self.catalogue.by_label(label)
        if playlist is None:
            raise HomeAssistantError(f"Unknown Drift playlist: {label}")
        if playlist.pattern_ids:
            pattern_id = playlist.pattern_ids[0]
        else:
            pattern_id = 0
            _LOGGER.info(
                "Playlist %s has no pattern ids; drawing it with pattern 0",
                playlist.protocol_id,
            )
        await self.async_send(draw_playlist(playlist.protocol_id, pattern_id))
        changes: dict[str, Any] = {"playlist_id": playlist.protocol_id, "status": 1}
        if pattern_id:
            changes["pattern_id"] = pattern_id
        self._replace(**changes)

    async def async_select_pattern(self, label: str) -> None:
        """Play one stored pattern. This does not change the power switch."""
        async with self._command_lock:
            self._require_awake()
            pattern_id = None
            for choice, stored in self.pattern_choices():
                if choice == label:
                    pattern_id = stored
                    break
            if pattern_id is None:
                raise HomeAssistantError(f"Unknown Drift pattern: {label}")
            clean_id = None
            if self.library.clean_before:
                clean_id = await self._ensure_clean_id()
                if not self.session_on:
                    return
            order = clean_play_order(
                pattern_id, clean_id, clean_before=self.library.clean_before
            )
            if order == [clean_id, pattern_id]:
                self._clean_follow += 1
                token = self._clean_follow
                await self.async_send(draw_pattern(clean_id))
                self._replace(pattern_id=clean_id, status=1)
                self.hass.async_create_task(
                    self._play_after_clean(token, pattern_id, clean_id),
                    name=f"{DOMAIN}-clean-then-{self.address}",
                )
                return
            await self.async_send(draw_pattern(pattern_id))
            self._replace(pattern_id=pattern_id, status=1)

    async def async_load_library(self) -> None:
        """Read names and uploaded patterns saved on this machine."""
        stored = await self._library_store.async_load()
        self.library = PatternLibrary.from_dict(stored if isinstance(stored, dict) else None)

    async def _save_library(self) -> None:
        await self._library_store.async_save(self.library.to_dict())

    def pattern_folder(self) -> Path:
        return Path(self.hass.config.path("drift_patterns"))

    def _preview_path(self, pattern_id: int) -> Path:
        slug = self.address.replace(":", "")
        return self.pattern_folder() / "previews" / f"{slug}-{pattern_id}.png"

    def pattern_choices(self) -> list[tuple[str, int]]:
        """Pattern select labels, including names saved on this machine."""
        ids = list(self.patterns.pattern_ids)
        for extra in self.library.uploaded_ids():
            if extra not in ids:
                ids.append(extra)
        return label_patterns(ids, self.library.names())

    def display_name(self, pattern_id: int) -> str | None:
        """Name for one id. Idle (0) has none."""
        if pattern_id <= 0:
            return None
        for label, stored in self.pattern_choices():
            if stored == pattern_id:
                return label
        return self.library.name_for(pattern_id) or f"Pattern {pattern_id}"

    def slot_counts(self) -> tuple[int, int]:
        used = len(self.patterns.pattern_ids)
        return used, max(0, STORAGE_CAP - used)

    async def async_refresh_inbox(self) -> None:
        """Look again for .thr files. This does not upload them."""
        await self._scan_inbox(None)

    async def _scan_inbox(self, _now: datetime | None = None) -> None:
        """List .thr files that have not been uploaded. This does not upload them."""
        folder = self.pattern_folder()

        def _names() -> list[str]:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "previews").mkdir(parents=True, exist_ok=True)
            if not folder.is_dir():
                return []
            return [item.name for item in folder.iterdir() if item.is_file()]

        try:
            names = await self.hass.async_add_executor_job(_names)
        except OSError:
            _LOGGER.debug("Drift pattern folder could not be read", exc_info=True)
            return
        self.inbox = inbox_names(names, self.library)
        if self.inbox_choice not in self.inbox:
            self.inbox_choice = self.inbox[0] if self.inbox else None
        self._publish()

    async def async_upload_inbox(self) -> None:
        """Upload the folder file the user picked. Nothing uploads until this runs."""
        choice = self.inbox_choice
        if not choice:
            raise HomeAssistantError("No .thr file is waiting in the pattern folder")
        path = self.pattern_folder() / choice
        name = path.stem
        await self.async_upload_pattern(name=name, path=str(path), source=choice)

    async def async_upload_pattern(
        self,
        *,
        name: str,
        path: str | None = None,
        thr: str | None = None,
        source: str = "",
        progress: Any = None,
    ) -> int:
        """Store a new pattern. Success is only the table's stored message."""
        cleaned = name.strip()
        if not cleaned:
            raise HomeAssistantError("The pattern needs a name")
        if path and thr:
            raise HomeAssistantError("Give a file path or the pattern text, not both")
        if path:
            try:
                file_path = path_under_config(Path(self.hass.config.path()), path)
            except PatternRejected as err:
                raise HomeAssistantError(err.message) from err
            if not file_path.is_file():
                raise HomeAssistantError("That pattern file was not found")

            def _read() -> str:
                return file_path.read_text(encoding="utf-8")

            text = await self.hass.async_add_executor_job(_read)
            source = source or file_path.name
        elif thr and thr.strip():
            text = thr
        else:
            raise HomeAssistantError("Give a .thr file path or the pattern text")
        try:
            polar_count_text = text
            wire = thr_to_wire(polar_count_text)
            pages = paginate(wire)
        except PatternRejected as err:
            raise HomeAssistantError(err.message) from err
        async with self._command_lock:
            playing = self.data.pattern_id if self.data is not None else None
            try:
                reuse = reusable_id(
                    self.library.id_for_upload_name(cleaned),
                    self.library.protected_ids(),
                )
                pattern_id = allocate_id(
                    set(self.patterns.pattern_ids),
                    playing=playing,
                    reuse=reuse,
                )
            except PatternRejected as err:
                raise HomeAssistantError(err.message) from err
            await self._transfer(pattern_id, pages, progress=progress)
            preview = self._preview_path(pattern_id)
            try:
                png = await self.hass.async_add_executor_job(render_thr, text)

                def _write() -> None:
                    preview.parent.mkdir(parents=True, exist_ok=True)
                    preview.write_bytes(png)

                await self.hass.async_add_executor_job(_write)
            except Exception:
                _LOGGER.warning("Drift preview was not saved for pattern %s", pattern_id, exc_info=True)
            self.library.remember(pattern_id, cleaned, text, source)
            await self._save_library()
            self.preview_at = datetime.now(timezone.utc)
            self._publish()
            await self._scan_inbox(None)
            return pattern_id

    async def _transfer(
        self,
        pattern_id: int,
        pages: list[list[tuple[int, int]]],
        progress: Any = None,
    ) -> None:
        """Send start, pages, and end. Only ``0x34/3`` is success.

        If the transfer stops after start, one end packet is sent so the table
        can close the file instead of sitting in an open upload.
        """
        started = False
        stored = False
        ended = False
        try:
            self._drain_notices()
            for attempt in range(1, 4):
                await self.async_send(start_upload(pattern_id, len(pages)))
                try:
                    message = await self._wait_notice(
                        4.0,
                        lambda notice: notice.kind
                        in (Kind.UPLOAD_STARTED, Kind.UPLOAD_FAILED, Kind.NO_STORAGE)
                        and notice.pattern_id == pattern_id,
                    )
                except TimeoutError:
                    if attempt == 3:
                        raise HomeAssistantError("The table did not start the upload") from None
                    continue
                if message.kind is Kind.UPLOAD_FAILED:
                    raise HomeAssistantError("The table rejected the upload")
                if message.kind is Kind.NO_STORAGE:
                    raise HomeAssistantError("The table has no room for another pattern")
                started = True
                break
            pending = list(range(len(pages)))
            delay = 0.1
            sent_pages = 0
            for attempt in range(1, 7):
                for index in pending:
                    await self.async_send(pattern_page(index + 1, pages[index]))
                    sent_pages += 1
                    if progress is not None:
                        progress(sent_pages, len(pages))
                    await asyncio.sleep(delay)
                await asyncio.sleep(delay)
                await self.async_send(end_upload(pattern_id, len(pages)))
                ended = True
                message = await self._wait_notice(
                    15.0,
                    lambda notice: (
                        notice.kind in (Kind.UPLOAD_STORED, Kind.UPLOAD_FAILED, Kind.NO_STORAGE)
                        and notice.pattern_id == pattern_id
                    )
                    or notice.kind is Kind.UPLOAD_MISSING,
                )
                if message.kind is Kind.UPLOAD_STORED:
                    stored = True
                    return
                if message.kind is Kind.UPLOAD_FAILED:
                    raise HomeAssistantError("The table rejected the pattern")
                if message.kind is Kind.NO_STORAGE:
                    raise HomeAssistantError("The table has no room for another pattern")
                pending = resend_indexes(len(pages), list(message.pages or []), attempt)
                delay = 0.2
            raise HomeAssistantError("The table did not confirm the pattern was stored")
        finally:
            if started and not stored and not ended:
                with contextlib.suppress(Exception):
                    await self.async_send(end_upload(pattern_id, len(pages)))

    def _drain_notices(self) -> None:
        while not self._notices.empty():
            self._notices.get_nowait()

    async def _wait_notice(self, timeout: float, predicate: Any) -> Message:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError
            notice = await asyncio.wait_for(self._notices.get(), remaining)
            if predicate(notice):
                return notice

    def _stock_clean_id(self) -> int | None:
        lists = [
            CleanList(item.index, item.name, item.pattern_ids)
            for item in self.catalogue.playlists
        ]
        return find_stock_clean(lists, self.library.names(), set(self.patterns.pattern_ids))

    async def _ensure_clean_id(self) -> int:
        """Stock clean pattern, or one tight spiral uploaded once and kept."""
        if not self.session_on:
            raise HomeAssistantError("Drift power is off")
        stock = self._stock_clean_id()
        if stock is not None:
            return stock
        playing = self.data.pattern_id if self.data is not None else None
        stored = set(self.patterns.pattern_ids)
        existing = self.library.protected_clean_id()
        if existing is not None and existing in stored and existing != playing:
            return existing
        pattern_id = choose_clean_upload_id(stored, playing, existing)
        points = cleaning_spiral()
        pages = paginate([wire_point(theta, rho) for theta, rho in points])
        await self._transfer(pattern_id, pages)
        text = spiral_thr(points)
        self.library.remember(pattern_id, "Clean", text, protected=True)
        await self._save_library()
        self.preview_at = datetime.now(timezone.utc)
        try:
            png = await self.hass.async_add_executor_job(render_thr, text)
            preview = self._preview_path(pattern_id)

            def _write() -> None:
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_bytes(png)

            await self.hass.async_add_executor_job(_write)
        except Exception:
            _LOGGER.warning("Drift clean preview was not saved", exc_info=True)
        self._publish()
        return pattern_id

    async def async_clean_sand(self) -> None:
        """Play the clean pattern. Power stays wherever the switch left it."""
        if not self.session_on:
            raise HomeAssistantError("Drift power is off")
        async with self._command_lock:
            if not self.session_on:
                return
            self._clean_follow += 1
            pattern_id = await self._ensure_clean_id()
            if not self.session_on:
                return
            await self.async_send(draw_pattern(pattern_id))
            self._replace(pattern_id=pattern_id, status=1)

    async def _wait_until_clean_done(self, token: int, clean_id: int) -> bool:
        """Wait until the wipe has been seen drawing and then goes idle.

        Status is already pushed by the table. Turning Power off cancels the wait.
        """
        seen = False
        deadline = asyncio.get_running_loop().time() + 20 * 60
        while asyncio.get_running_loop().time() < deadline:
            if token != self._clean_follow or not self.session_on:
                return False
            data = self.data
            if data is not None and data.pattern_id == clean_id and data.drawing:
                seen = True
            if seen and data is not None and not data.drawing:
                return True
            await asyncio.sleep(0.5)
        return False

    async def _play_after_clean(self, token: int, pattern_id: int, clean_id: int) -> None:
        """After the wipe finishes, play the pattern the user picked."""
        if not await self._wait_until_clean_done(token, clean_id):
            return
        await self._play_if_on(pattern_id, True)

    async def async_set_clean_before(self, enabled: bool) -> None:
        """Remember whether a new pattern should wipe the sand first."""
        self.library.clean_before = bool(enabled)
        await self._save_library()
        self._publish()

    async def async_delete_pattern(self, *, pattern_id: int | None = None, name: str | None = None) -> None:
        """Delete one pattern this integration uploaded, never a stock id or the one drawing."""
        async with self._command_lock:
            target = pattern_id
            if target is None and name:
                target = self.library.id_for_upload_name(name.strip())
            if target is None:
                raise HomeAssistantError("Name the uploaded pattern to delete")
            playing = self.data.pattern_id if self.data is not None else None
            reason = deletion_refusal(
                target,
                stored=set(self.patterns.pattern_ids),
                playing=playing,
                uploaded=self.library.uploaded_ids(),
                protected=self.library.protected_ids(),
            )
            if reason is not None:
                raise HomeAssistantError(reason)
            self._drain_notices()
            await self.async_send(delete_patterns([target]))
            try:
                await self._wait_notice(
                    8.0,
                    lambda notice: notice.kind is Kind.DELETE_COMPLETE and notice.pattern_id == target,
                )
            except TimeoutError as err:
                raise HomeAssistantError("The table did not confirm the delete") from err
            self.library.forget(target)
            preview = self._preview_path(target)
            with contextlib.suppress(OSError):
                await self.hass.async_add_executor_job(preview.unlink, True)
            await self._save_library()
            self.preview_at = datetime.now(timezone.utc)
            self._publish()

    def _task_states(self) -> list[tuple[str, str]]:
        states: list[tuple[str, str]] = []
        for entity_id in self.hass.states.async_entity_ids("ai_task"):
            state = self.hass.states.get(entity_id)
            states.append((entity_id, state.state if state else "unavailable"))
        return states

    def _conversation_agents(self) -> list[tuple[str, str]]:
        try:
            from homeassistant.components.conversation import async_get_agent_info
        except ImportError:
            return []
        try:
            infos = async_get_agent_info(self.hass)
        except Exception:
            return []
        found: list[tuple[str, str]] = []
        for info in infos or []:
            agent_id = getattr(info, "id", None)
            if not agent_id:
                continue
            found.append((str(agent_id), str(getattr(info, "name", None) or agent_id)))
        return found

    def _preferred_ai_task(self) -> str | None:
        preferences = self.hass.data.get("ai_task_preferences")
        entity_id = getattr(preferences, "gen_data_entity_id", None)
        return str(entity_id) if entity_id else None

    def drawing_assistant(self) -> tuple[str, str] | None:
        """The explicit assistant for one drawing, or None when nothing can draw."""
        options = self.config_entry.options
        try:
            return choose_drawing_assistant(
                configured_task=options.get(CONF_AI_TASK_ENTITY),
                configured_agent=options.get(CONF_CONVERSATION_AGENT),
                preferred_task=self._preferred_ai_task(),
                task_states=self._task_states(),
                agents=self._conversation_agents(),
            )
        except PatternRejected:
            return None

    def ai_available(self) -> bool:
        """True when a real AI Task or an extra conversation agent can draw.

        This integration does not store an API key. The button stays off when
        nothing can be named explicitly.
        """
        return self.drawing_assistant() is not None

    def _set_ai(self, status: str, *, error: str = "", detail: str = "", name: str = "", pattern_id: int | None = None) -> None:
        self.ai_status = status
        self.ai_error = error
        self.ai_detail = detail
        if name:
            self.ai_name = name
        self.ai_pattern_id = pattern_id
        self._publish()

    async def _ask_model(self, kind: str, target: str, prompt: str) -> str:
        """One model call to an assistant that was already chosen."""
        instructions = build_instructions(prompt)
        if kind == "ai_task":
            if not self.hass.services.has_service("ai_task", "generate_data"):
                raise HomeAssistantError(
                    "Home Assistant has an AI Task entity but the AI Task service is not ready"
                )
            try:
                result = await self.hass.services.async_call(
                    "ai_task",
                    "generate_data",
                    {
                        "task_name": "Drift sand drawing",
                        "instructions": instructions,
                        "entity_id": target,
                        "structure": {
                            "path": {
                                "description": "JSON list of [x, y] pairs between -1 and 1",
                                "selector": {"text": {"multiline": True}},
                            }
                        },
                    },
                    blocking=True,
                    return_response=True,
                )
            except HomeAssistantError:
                raise
            except Exception as err:
                raise HomeAssistantError(f"AI Task could not draw that: {err}") from err
            return model_text(result)
        if not self.hass.services.has_service("conversation", "process"):
            raise HomeAssistantError(
                "No AI Task is available, and the conversation service is not ready"
            )
        try:
            result = await self.hass.services.async_call(
                "conversation",
                "process",
                {"text": instructions, "agent_id": target},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"The conversation agent could not draw that: {err}") from err
        return model_text(result)

    def _assistant_label(self, kind: str, target: str) -> str:
        if kind == "ai_task":
            state = self.hass.states.get(target)
            if state is not None and state.name:
                return state.name
        for agent_id, label in self._conversation_agents():
            if agent_id == target:
                return label
        return target

    def _announce(
        self,
        stage: str,
        *,
        prompt: str = "",
        assistant: str = "",
        percent: int | None = None,
        name: str = "",
        playing: bool = False,
        error: str = "",
    ) -> None:
        """Update the notification, the sensor, and the status event together."""
        message = feedback_text(
            stage,
            prompt=prompt,
            assistant=assistant,
            percent=percent,
            name=name,
            playing=playing,
            error=error,
        )
        if stage == "uploading" and percent is not None:
            self.ai_progress = percent
        elif stage == "done":
            self.ai_progress = 100
        elif stage == "drawing":
            self.ai_progress = 0
        elif stage == "error":
            self.ai_progress = None
        self._publish()
        self.hass.bus.async_fire(
            "homedics_drift_ai_status",
            {
                "stage": stage,
                "progress": self.ai_progress,
                "message": message,
                "name": name,
                "prompt": prompt,
                "assistant": assistant,
                "playing": playing,
            },
        )
        self.hass.async_create_task(
            self._post_notice(message),
            name=f"{DOMAIN}-notice-{self.address}",
        )

    async def _post_notice(self, message: str) -> None:
        """Create or replace the one Drift drawing notification. It can stay."""
        with contextlib.suppress(Exception):
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": f"{DOMAIN}_draw_{self.address.replace(':', '_')}",
                    "title": "Drift",
                    "message": message,
                },
                blocking=False,
            )

    def _reject_if_busy(self) -> None:
        if not self._draw_active:
            return
        self._announce("busy")
        raise HomeAssistantError("A drawing is already in progress")

    def _note_upload(self, done: int, total: int, name: str) -> None:
        for percent in self._upload_ticks.crossed(done, total):
            self._announce("uploading", percent=percent, name=name)

    async def async_ai_draw(self, prompt: str, *, name: str | None = None, play: bool = False) -> int:
        """Ask the configured assistant for one path, then upload it."""
        self._reject_if_busy()
        cleaned = " ".join(prompt.split())
        if not cleaned:
            raise HomeAssistantError("Type a prompt first")
        title = (name or cleaned[:40]).strip()
        self._draw_active = True
        self._upload_ticks = UploadTicks()
        self._set_ai("running", name=title)
        try:
            kind, target = choose_drawing_assistant(
                configured_task=self.config_entry.options.get(CONF_AI_TASK_ENTITY),
                configured_agent=self.config_entry.options.get(CONF_CONVERSATION_AGENT),
                preferred_task=self._preferred_ai_task(),
                task_states=self._task_states(),
                agents=self._conversation_agents(),
            )
            assistant = self._assistant_label(kind, target)
            self._announce("drawing", prompt=cleaned, assistant=assistant, name=title)
            raw = await self._ask_model(kind, target, cleaned)
            try:
                thr = path_from_model(raw)
            except PatternRejected as err:
                raise HomeAssistantError(err.message) from err
            pattern_id = await self.async_upload_pattern(
                name=title,
                thr=thr,
                source="ai",
                progress=lambda done, total: self._note_upload(done, total, title),
            )
            playing = False
            if clean_before_ai_drawing(
                self.config_entry.options.get(CONF_CLEAN_BEFORE_AI, True),
                play=play,
                power_on=self.session_on,
            ):
                self._announce(
                    "cleaning",
                    prompt=cleaned,
                    assistant=assistant,
                    name=title,
                )
                clean_id = await self._ensure_clean_id()
                if self.session_on and clean_id != pattern_id:
                    self._clean_follow += 1
                    token = self._clean_follow
                    async with self._command_lock:
                        if self.session_on:
                            await self.async_send(draw_pattern(clean_id))
                            self._replace(pattern_id=clean_id, status=1)
                    if await self._wait_until_clean_done(token, clean_id):
                        playing = await self._play_if_on(pattern_id, True)
                else:
                    playing = await self._play_if_on(pattern_id, True)
            else:
                playing = await self._play_if_on(pattern_id, play)
            detail = "" if playing or not play else "Power is off, so the pattern was saved but not played"
            self._set_ai("stored", detail=detail, name=title, pattern_id=pattern_id)
            self._announce("done", name=title, playing=playing, prompt=cleaned, assistant=assistant)
            return pattern_id
        except HomeAssistantError as err:
            self._set_ai("error", error=str(err), name=title)
            self._announce("error", error=str(err), name=title, prompt=cleaned)
            raise
        finally:
            self._draw_active = False

    async def _play_if_on(self, pattern_id: int, play: bool) -> bool:
        """Start the pattern only while Power is already on."""
        if not play or not self.session_on:
            return False
        async with self._command_lock:
            if not self.session_on:
                return False
            await self.async_send(draw_pattern(pattern_id))
            self._replace(pattern_id=pattern_id, status=1)
        return True

    async def async_generate_pattern(
        self,
        kind: str,
        params: dict[str, object] | None = None,
        *,
        name: str | None = None,
        play: bool = False,
    ) -> int:
        """Upload a built-in curve. No model is called."""
        title = (name or kind).strip()
        self._set_ai("running", name=title)
        try:
            try:
                thr = generated_thr(kind, params)
            except PatternRejected as err:
                raise HomeAssistantError(err.message) from err
            pattern_id = await self.async_upload_pattern(name=title, thr=thr, source="generated")
            detail = ""
            if play and self.session_on:
                async with self._command_lock:
                    if self.session_on:
                        await self.async_send(draw_pattern(pattern_id))
                        self._replace(pattern_id=pattern_id, status=1)
            elif play:
                detail = "Power is off, so the pattern was saved but not played"
            self._set_ai("stored", detail=detail, name=title, pattern_id=pattern_id)
            return pattern_id
        except HomeAssistantError as err:
            self._set_ai("error", error=str(err), name=title)
            raise

    async def async_add_gallery_design(self, name: str, *, play: bool = False) -> int:
        """Save one shipped design and upload it. Play only while Power is on."""
        thr = gallery_thr(name)
        return await self._upload_thr(name, thr, play=play, source="gallery")

    async def async_random_gallery(self) -> int:
        """Upload a seeded variation. The same seed is not reused on purpose."""
        import random as _random

        seed = _random.SystemRandom().randrange(1, 1_000_000_000)
        title, thr = random_gallery(seed)
        return await self._upload_thr(title, thr, play=self.session_on, source="gallery-random")

    async def async_set_favorite(self, name: str, on: bool) -> None:
        """Remember a design the user likes. Nothing is sent to the table."""
        try:
            self.library.set_favorite(name, on)
        except PatternRejected as err:
            raise HomeAssistantError(err.message) from err
        await self._save_library()
        self._publish()

    async def async_open_favorite(self, name: str) -> None:
        """Play a saved favorite. Power is not turned on."""
        if name in gallery_names():
            await self.async_add_gallery_design(name, play=self.session_on)
            return
        pattern_id = self.library.id_for_upload_name(name)
        if pattern_id is None:
            raise HomeAssistantError(f"Unknown favorite: {name}")
        if not self.session_on:
            raise HomeAssistantError("Drift power is off")
        async with self._command_lock:
            if not self.session_on:
                return
            await self.async_send(draw_pattern(pattern_id))
            self._replace(pattern_id=pattern_id, status=1)

    async def async_import_pattern_url(self, url: str) -> int:
        """Download .thr files the user chose and upload the ones that fit.

        Community files are not shipped with this integration. A file that is
        too long is skipped. The clean pattern is never replaced.
        """
        try:
            checked = https_pattern_url(url)
        except PatternRejected as err:
            raise HomeAssistantError(err.message) from err
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(checked, timeout=30) as response:
                if response.status != 200:
                    raise HomeAssistantError("That pattern link could not be downloaded")
                body = await response.read()
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError("That pattern link could not be downloaded") from err
        try:
            documents = documents_from_download(checked, body)
        except PatternRejected as err:
            raise HomeAssistantError(err.message) from err
        stored = 0
        skipped: list[str] = []
        for name, text in documents:
            if self.slot_counts()[1] <= 0 and self.library.id_for_upload_name(name) is None:
                skipped.append(name)
                break
            try:
                await self.async_upload_pattern(name=name, thr=text, source="import")
            except HomeAssistantError:
                skipped.append(name)
                continue
            stored += 1
        if stored == 0:
            raise HomeAssistantError(
                "Nothing from that link could be stored. Files must be .thr patterns short enough for the table."
            )
        if skipped:
            self.ai_detail = "Skipped: " + ", ".join(skipped[:8])
            self._publish()
        return stored

    async def _upload_thr(self, name: str, thr: str, *, play: bool, source: str) -> int:
        self._reject_if_busy()
        self._draw_active = True
        self._upload_ticks = UploadTicks()
        try:
            pattern_id = await self.async_upload_pattern(
                name=name,
                thr=thr,
                source=source,
                progress=lambda done, total: self._note_upload(done, total, name),
            )
            playing = await self._play_if_on(pattern_id, play)
            self._announce("done", name=name, playing=playing)
            return pattern_id
        except HomeAssistantError as err:
            self._announce("error", error=str(err), name=name)
            raise
        finally:
            self._draw_active = False

    async def async_rename_pattern(self, pattern_id: int, name: str) -> None:
        """Remember a display name. Nothing is sent to the table."""
        try:
            self.library.rename(pattern_id, name)
        except PatternRejected as err:
            raise HomeAssistantError(err.message) from err
        await self._save_library()
        self._publish()

    def preview_bytes(self) -> bytes | None:
        """PNG for the pattern that is on now, when this machine has one."""
        if self.data is None or self.data.pattern_id <= 0:
            return None
        path = self._preview_path(self.data.pattern_id)
        if not path.is_file():
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    async def _async_update_data(self) -> DriftState:
        if self.data is None:
            raise UpdateFailed("Drift table is not connected")
        return self.data

    async def _disconnect_client(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        with contextlib.suppress(Exception):
            if client.is_connected:
                await client.stop_notify(NOTIFY_UUID)
        with contextlib.suppress(Exception):
            await client.disconnect()
