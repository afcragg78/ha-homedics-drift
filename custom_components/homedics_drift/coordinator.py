"""Persistent Bluetooth session for one Drift table."""

from __future__ import annotations

import asyncio
import contextlib
import logging
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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BACKOFF_MAX,
    BACKOFF_START,
    DOMAIN,
    NOTIFY_UUID,
    READY_TIMEOUT,
    WRITE_UUID,
)
from .protocol import (
    CMD_PLAYLIST_LIST,
    DriftState,
    Kind,
    PlaylistCatalogue,
    alarm_text,
    brightness,
    draw_playlist,
    fixed_color,
    next_pattern,
    play_pause,
    power,
    previous_pattern,
    reply_for,
    speed_raw,
    Packet,
    PacketParser,
    percent_to_speed_raw,
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
        self.lamp_brightness = 100
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
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
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
        if message.kind is Kind.WAITING:
            self._ready.clear()
            self._publish()
            return
        if message.kind is Kind.INIT_COMPLETE:
            if not self._ready.is_set():
                _LOGGER.info(
                    "Drift %s session ready (%s playlist(s))",
                    self.address,
                    len(self.catalogue.playlists),
                )
            self._ready.set()
            self._publish()
            return
        if message.kind is Kind.STATE and message.state is not None:
            if message.state.brightness > 0:
                self.lamp_brightness = message.state.brightness
            self.async_set_updated_data(message.state)
            return
        if message.kind in (Kind.PLAYLIST, Kind.PLAYLIST_RESET):
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

    async def async_set_power(self, on: bool) -> None:
        """Soft power, command 0x14/16. This is not a mains plug."""
        await self.async_send(power(on))
        self._replace(power_on=on)

    async def async_toggle_playback(self) -> None:
        """Send the protocol's play/pause toggle."""
        drawing = bool(self.data and self.data.drawing)
        await self.async_send(play_pause())
        self._replace(status=0 if drawing else 1)

    async def async_next(self) -> None:
        await self.async_send(next_pattern())

    async def async_previous(self) -> None:
        await self.async_send(previous_pattern())

    async def async_set_speed_percent(self, percent: float) -> None:
        raw = percent_to_speed_raw(percent)
        await self.async_send(speed_raw(raw))
        self._replace(speed_raw=raw)

    async def async_set_brightness(self, level: int) -> None:
        level = max(0, min(100, int(level)))
        await self.async_send(brightness(level))
        if level > 0:
            self.lamp_brightness = level
        self._replace(brightness=level)

    async def async_set_color(self, rgb: tuple[int, int, int], level: int) -> None:
        """Store a fixed colour as palette entry Temp so it survives disconnect."""
        level = max(1, min(100, int(level)))
        red, green, blue = (max(0, min(255, int(channel))) for channel in rgb)
        for packet in fixed_color(red, green, blue, level):
            await self.async_send(packet)
        self.lamp_brightness = level
        self._replace(
            color=(red, green, blue),
            color_name="Temp",
            brightness=level,
            shifting=False,
            breathing=False,
            shift_time=0,
        )

    async def async_select_playlist(self, label: str) -> None:
        """Draw the playlist the table reported under ``label``."""
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
