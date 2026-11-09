"""Drift sand-table packet codec.

Josh Lannin's Drifted project (https://github.com/joshlannin/drifted, MIT,
copyright Altimix LLC) reverse-engineered this protocol. This Home Assistant
integration was converted from Drifted using Grok Bot. It does not send
firmware-update commands (0x15) or the reserved controller reset (0x14/12).

Playlist packets (table command 0x30, actions 1..4) are the playlist list
the table sends during the session dump on every connection. Host command
0x10 writes playlist definitions and is intentionally not sent, because that
would replace the lists stored on the table. The 0x30 payload is
"strings" and "u16 arrays", in the same page/count framing as colour pages
(0x31/3) and stored-pattern pages (0x33). Several layouts are accepted, in
the order below, and the first one that consumes the payload exactly wins:

1. ``page, count, count × (name, pattern-id array)``
2. ``page, count, count × (index, name, pattern-id array)``
3. ``page, pattern-id-style u16 array`` of playlist indices and no names
4. ``page, count, count × name``

A missing name is shown as ``Playlist N``. The string sent with draw-from-playlist
(0x14/2) is the name when the table provided one, otherwise the decimal index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

FRAME = 0x7B
ACK_BIT = 0x80
MAX_PACKET_LENGTH = 199
POINTS_PER_PAGE = 40

CMD_PLAYLIST_WRITE = 0x10
CMD_LIGHTING = 0x11
CMD_TIME = 0x12
CMD_FILE = 0x13
CMD_ACTION = 0x14
CMD_FIRMWARE = 0x15
CMD_PLAYLIST_LIST = 0x30
CMD_PATTERNS = 0x33
CMD_UPLOAD = 0x34
CMD_STATE = 0x35
CMD_ALARM = 0x37
CMD_INIT = 0x4F
CMD_CONNECTION = 0x50
CMD_PAGE = 0x53

ACTION_RESET = 12

ALARM_NAMES: dict[int, str] = {
    1: "file queue full",
    2: "setting coordinates failed",
    3: "file download failed",
    4: "SD card full",
    5: "file already open",
    6: "too much file data lost",
    8: "motor driver error",
    9: "SD card init failed",
    10: "can't open pattern file",
    11: "can't read pattern file",
    12: "can't close pattern file",
    13: "can't delete pattern file",
    14: "file seek failed",
    15: "position reset failed",
    16: "homing failed",
    17: "can't create received file",
    19: "receive queue error",
}

SPEED_RAW_MIN = 30
SPEED_RAW_MAX = 75


class ProtocolError(ValueError):
    """A packet could not be encoded or decoded."""


def checksum(body: bytes) -> int:
    """Return the protocol checksum, the low eight bits of the byte sum."""
    return sum(body) & 0xFF


def _is_printable(text: str) -> bool:
    return all(char.isprintable() for char in text)


@dataclass(frozen=True, slots=True)
class Packet:
    """One framed message: ``7B len ackCmd data checksum``."""

    command: int
    data: bytes = b""
    ack: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", self.command & 0x7F)
        object.__setattr__(self, "data", bytes(self.data))

    @property
    def action(self) -> int | None:
        """Action byte, when the payload has one."""
        return self.data[0] if self.data else None

    @property
    def arguments(self) -> bytes:
        """Payload after the action byte."""
        return self.data[1:]

    def encode(self) -> bytes:
        """Encode one packet. Refuses firmware update and the reserved reset."""
        if self.command == CMD_FIRMWARE:
            raise ProtocolError("refusing to send firmware update command 0x15")
        if self.command == CMD_ACTION and self.action == ACTION_RESET:
            raise ProtocolError("refusing to send reserved reset command 0x14/12")
        length = len(self.data) + 4
        if length > MAX_PACKET_LENGTH:
            raise ProtocolError(f"packet length {length} exceeds {MAX_PACKET_LENGTH}")
        ack_cmd = self.command | ACK_BIT if self.ack else self.command
        body = bytes((FRAME, length, ack_cmd)) + self.data
        return body + bytes((checksum(body),))


def _checksum_matches(raw: bytes) -> bool:
    body, received = raw[:-1], raw[-1]
    if checksum(body) == received:
        return True
    # The table sometimes checksums the command with the ack bit cleared.
    stripped = bytearray(body)
    stripped[2] &= 0x7F
    return checksum(stripped) == received


class PacketParser:
    """Reassemble a notify byte stream into packets.

    Notifications may split a packet or carry several. Bytes before the next
    frame marker, and frames whose checksum matches neither variant, are dropped.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.dropped_bytes = 0
        self.checksum_failures = 0

    def feed(self, chunk: bytes) -> list[Packet]:
        self._buffer.extend(chunk)
        packets: list[Packet] = []
        while True:
            start = self._buffer.find(FRAME)
            if start < 0:
                self.dropped_bytes += len(self._buffer)
                self._buffer.clear()
                break
            if start:
                self.dropped_bytes += start
                del self._buffer[:start]
            if len(self._buffer) < 2:
                break
            length = self._buffer[1]
            if length < 4 or length > MAX_PACKET_LENGTH:
                self.dropped_bytes += 1
                del self._buffer[:1]
                continue
            if len(self._buffer) < length:
                break
            raw = bytes(self._buffer[:length])
            if _checksum_matches(raw):
                del self._buffer[:length]
                ack_cmd = raw[2]
                packets.append(
                    Packet(
                        command=ack_cmd & 0x7F,
                        data=raw[3:-1],
                        ack=bool(ack_cmd & ACK_BIT),
                    )
                )
            else:
                self.checksum_failures += 1
                self.dropped_bytes += 1
                del self._buffer[:1]
        return packets


class _Writer:
    def __init__(self) -> None:
        self.buf = bytearray()

    def u8(self, value: int) -> None:
        self.buf.append(value & 0xFF)

    def boolean(self, value: bool) -> None:
        self.u8(1 if value else 0)

    def u16(self, value: int) -> None:
        self.buf.append(value & 0xFF)
        self.buf.append((value >> 8) & 0xFF)

    def u32(self, value: int) -> None:
        for shift in range(0, 32, 8):
            self.buf.append((value >> shift) & 0xFF)

    def text(self, value: str) -> None:
        self.buf.extend(value.encode("utf-8"))
        self.buf.append(0)

    def u16_array(self, values: list[int]) -> None:
        if len(values) > 255:
            raise ProtocolError("u16 array longer than 255")
        self.u8(len(values))
        for value in values:
            self.u16(value)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.index = 0

    def remaining(self) -> int:
        return len(self.data) - self.index

    def u8(self) -> int:
        if self.index >= len(self.data):
            raise ProtocolError("truncated packet")
        value = self.data[self.index]
        self.index += 1
        return value

    def boolean(self) -> bool:
        return self.u8() != 0

    def u16(self) -> int:
        if self.index + 2 > len(self.data):
            raise ProtocolError("truncated packet")
        value = self.data[self.index] | (self.data[self.index + 1] << 8)
        self.index += 2
        return value

    def text(self) -> str:
        end = self.data.find(0, self.index)
        if end < 0:
            raise ProtocolError("unterminated string")
        raw = self.data[self.index : end]
        self.index = end + 1
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as err:
            raise ProtocolError("string is not utf-8") from err
        if not _is_printable(value):
            raise ProtocolError("string is not printable")
        return value

    def rgb(self) -> tuple[int, int, int]:
        return (self.u8(), self.u8(), self.u8())

    def u16_array(self) -> list[int]:
        count = self.u8()
        return [self.u16() for _ in range(count)]

    def finished(self) -> bool:
        return self.index == len(self.data)

    def _optional(self, read):  # noqa: ANN001
        mark = self.index
        try:
            return read()
        except ProtocolError:
            self.index = mark
            return None


def _packet(command: int, action: int | None = None, ack: bool = False) -> _Writer:
    writer = _Writer()
    if action is not None:
        writer.u8(action)
    return writer


def _finish(command: int, writer: _Writer, ack: bool = False) -> Packet:
    return Packet(command, bytes(writer.buf), ack)


def confirm_data() -> Packet:
    """Generic acknowledgement: ``7B 04 D0 4F``."""
    return Packet(CMD_CONNECTION, b"", ack=True)


def confirm_connection(ok: bool = True) -> Packet:
    """Reply to the table's waiting-for-confirm message."""
    writer = _packet(CMD_CONNECTION, 2)
    writer.boolean(ok)
    return _finish(CMD_CONNECTION, writer)


def current_time(moment: datetime | None = None) -> Packet:
    """Wall-clock time. Month is 0-based and Monday is weekday 1."""
    moment = moment or datetime.now()
    writer = _packet(CMD_TIME, 2)
    writer.u8(moment.year % 100)
    writer.u8(moment.month - 1)
    writer.u8(moment.day)
    writer.u8(moment.hour)
    writer.u8(moment.minute)
    writer.u8(moment.second)
    writer.u8(moment.weekday() + 1)
    return _finish(CMD_TIME, writer)


def power(on: bool) -> Packet:
    """Command ``0x14/16``. Drifted documents this as a power bool.

    On the ST-300 it does not clear ``powerOn``. Value 0 pauses the ball and
    the flag stays true, so the integration does not use this packet for the
    power switch.
    """
    writer = _packet(CMD_ACTION, 16)
    writer.boolean(bool(on))
    return _finish(CMD_ACTION, writer)


def play_pause() -> Packet:
    return Packet(CMD_ACTION, bytes((3,)))


def next_pattern() -> Packet:
    return Packet(CMD_ACTION, bytes((4,)))


def previous_pattern() -> Packet:
    return Packet(CMD_ACTION, bytes((5,)))


def speed_raw(raw: int) -> Packet:
    writer = _packet(CMD_ACTION, 6)
    writer.u8(raw)
    return _finish(CMD_ACTION, writer)


def percent_to_speed_raw(percent: float) -> int:
    """Map 0..100 percent onto the table's raw speed range 30..75."""
    fraction = min(100.0, max(0.0, percent)) / 100.0
    return SPEED_RAW_MIN + int(round(fraction * (SPEED_RAW_MAX - SPEED_RAW_MIN)))


def speed_raw_to_percent(raw: int) -> float:
    clamped = min(SPEED_RAW_MAX, max(SPEED_RAW_MIN, raw))
    return (clamped - SPEED_RAW_MIN) * 100.0 / (SPEED_RAW_MAX - SPEED_RAW_MIN)


def speed_percent(percent: float) -> Packet:
    return speed_raw(percent_to_speed_raw(percent))


def brightness(level: int) -> Packet:
    writer = _packet(CMD_ACTION, 7)
    writer.u8(max(0, min(100, int(level))))
    return _finish(CMD_ACTION, writer)


def show_color(red: int, green: int, blue: int, *, enabled: bool = True) -> Packet:
    """Show a colour and store it as palette entry ``Temp``.

    ``enabled`` is required. Omitting it shifts the colour bytes and turns
    white into yellow.
    """
    writer = _packet(CMD_ACTION, 15)
    writer.boolean(enabled)
    writer.u8(red)
    writer.u8(green)
    writer.u8(blue)
    return _finish(CMD_ACTION, writer)


def select_color(name: str) -> Packet:
    writer = _packet(CMD_ACTION, 13)
    writer.text(name)
    return _finish(CMD_ACTION, writer)


def light_mode(
    *,
    shifting: bool,
    shift_time: int,
    breathing: bool,
    brightness_level: int,
) -> Packet:
    writer = _packet(CMD_LIGHTING, 4)
    writer.boolean(shifting)
    writer.u16(shift_time)
    writer.boolean(breathing)
    writer.u8(max(0, min(100, int(brightness_level))))
    return _finish(CMD_LIGHTING, writer)


def fixed_color(red: int, green: int, blue: int, brightness_level: int) -> list[Packet]:
    """Drifted's colour recipe: preview, select ``Temp``, then light mode.

    This is the order ``settingsPackets`` sends for a colour. Brightness here
    is the persisted ``0x11/4`` value and is never zero when turning the lamp on.
    """
    level = max(1, min(100, int(brightness_level)))
    return [
        show_color(red, green, blue, enabled=True),
        select_color("Temp"),
        light_mode(
            shifting=False,
            shift_time=0,
            breathing=False,
            brightness_level=level,
        ),
    ]


@dataclass(frozen=True, slots=True)
class LampHold:
    """Lamp command waiting for the table to echo it.

    The 2 Hz status packet can still carry the previous brightness after the
    lamp has physically switched. Holding the command stops that stale report
    from turning the Home Assistant toggle back on, or back off.
    """

    on: bool
    level: int


def reconcile_lamp(reported: int, hold: LampHold | None) -> tuple[int, bool, LampHold | None]:
    """Combine a reported brightness with a command that has not been echoed.

    Brightness 0 is off. A held off command stays off while the report is
    still non-zero. A held on command stays on while the report is still 0.
    A report that agrees with the command clears the hold.
    """
    reported = max(0, min(100, int(reported)))
    if hold is None:
        return reported, reported > 0, None
    if hold.on:
        if reported > 0:
            return reported, True, None
        return max(1, hold.level), True, hold
    if reported <= 0:
        return 0, False, None
    return 0, False, hold


def parse_light_mode_echo(arguments: bytes) -> tuple[bool, int, bool, int] | None:
    """Parse ``0x31/4``, the table's echo of light mode.

    The layout matches ``0x11/4``: shifting, shift time in seconds, breathing,
    brightness 0..100. Brightness 0 is the lamp off.
    """
    reader = _Reader(arguments)
    try:
        shifting = reader.boolean()
        shift_time = reader.u16()
        breathing = reader.boolean()
        level = reader.u8()
    except ProtocolError:
        return None
    return shifting, shift_time, breathing, max(0, min(100, level))


def resolved_lamp_level(requested: int | None, remembered: int) -> int:
    """Brightness to use when turning the lamp on.

    An omitted or zero request restores the last non-zero level, or 100 when
    the table has never reported one. The result is always 1..100.
    """
    if requested is not None and requested > 0:
        return max(1, min(100, int(requested)))
    if remembered > 0:
        return max(1, min(100, int(remembered)))
    return 100


def lamp_on_packets(
    *,
    level: int,
    color: tuple[int, int, int],
    color_name: str,
    shifting: bool,
    shift_time: int,
    breathing: bool,
    from_off: bool,
) -> list[Packet]:
    """Turn the lamp on the way Drifted sets a brightness, then the live level.

    Drifted's settings path persists brightness with ``0x11/4`` only. On this
    table, off is ``0x14/7`` with value 0, and that live level stays 0 until
    ``0x14/7`` is sent again with a non-zero value. There is no separate light
    enable flag; ``0x14/15``'s enable byte only applies to a colour preview.
    Coming back from off therefore sends Drifted's colour recipe (preview,
    select ``Temp``, light mode at the restored brightness) and then ``0x14/7``
    with that same non-zero brightness. ``color_name`` is unused here: a
    palette name is not what relights the LEDs.
    """
    del color_name  # palette name is not part of Drifted's turn-on sequence
    level = max(1, min(100, int(level)))
    red, green, blue = color
    if from_off:
        return [
            *fixed_color(red, green, blue, level),
            brightness(level),
        ]
    return [
        light_mode(
            shifting=shifting,
            shift_time=shift_time,
            breathing=breathing,
            brightness_level=level,
        ),
        brightness(level),
    ]


def playback_allowed(session_on: bool) -> bool:
    """Play, pause, skip, and playlist picks are ignored while the switch is off."""
    return bool(session_on)


# Controls the player may expose. Power is never one of them.
PLAYER_CONTROLS_ON = frozenset({"play", "pause", "next", "previous"})


def player_controls(session_on: bool) -> frozenset[str]:
    """Buttons the player shows.

    While the power switch is off there are none, so the card has no Play
    control. Power on brings play, pause, next, and previous back. The player
    never offers its own power button or a source list.
    """
    if not session_on:
        return frozenset()
    return PLAYER_CONTROLS_ON


def transport_action(action: str, session_on: bool, *, drawing: bool) -> tuple[bool, str | None]:
    """What a player button is allowed to do.

    Pause only pauses, and only while power is already on. Play never turns
    power on. Only ``power_on`` and ``power_off`` change the switch, and those
    are the power switch, not the player.
    """
    if action == "pause":
        if session_on and drawing:
            return session_on, "pause"
        return session_on, None
    if action == "play":
        if session_on and not drawing:
            return session_on, "resume"
        return session_on, None
    if action == "next" or action == "previous":
        if session_on:
            return session_on, action
        return session_on, None
    if action == "power_on":
        return True, "session_on"
    if action == "power_off":
        return False, "session_off"
    return session_on, None


class StopAfterWatch:
    """Pause when a design finishes. Power and the lamp are not touched.

    A user play, skip, or pattern choice grants the next pattern change so the
    table can start that design. After it reaches the end, or advances by
    itself, the next observe asks for a pause.
    """

    def __init__(self) -> None:
        self.enabled = False
        self.pattern_id: int | None = None
        self.grants = 0
        self.allow_finish = False
        self.pausing = False

    def authorize(self, pattern_changes: int = 1) -> None:
        """Let the user start a design. ``pattern_changes`` covers a wipe then the design."""
        self.grants += max(1, pattern_changes)
        self.allow_finish = True
        self.pausing = False

    def observe(
        self,
        *,
        session_on: bool,
        drawing: bool,
        progress: float,
        pattern_id: int,
    ) -> bool:
        """True when pause should be sent. Never means power off or lamp off."""
        if not self.enabled or not session_on:
            self.pattern_id = pattern_id
            self.pausing = False
            self.allow_finish = False
            return False
        if not drawing:
            self.pausing = False
            if pattern_id > 0:
                self.pattern_id = pattern_id
            return False
        if self.pattern_id is not None and pattern_id != self.pattern_id and pattern_id > 0:
            if self.grants > 0:
                self.grants -= 1
                self.pattern_id = pattern_id
                self.allow_finish = True
                self.pausing = False
                return False
            self.pattern_id = pattern_id
            self.pausing = True
            return True
        if self.pattern_id is None:
            self.pattern_id = pattern_id
        if self.allow_finish:
            if progress < 0.95:
                self.allow_finish = False
            return False
        if progress >= 0.999 and not self.pausing:
            self.pausing = True
            return True
        return False


def shown_playback(session_on: bool, drawing: bool, *, settled: bool = True) -> str:
    """Player state owned by the integration switch, not by ``powerOn``.

    Off stays off while a command is in flight and while the switch is off,
    even if the table still says it is drawing or pauses and then draws again.
    """
    if not session_on or not settled:
        return "off"
    if drawing:
        return "playing"
    return "paused"


def lamp_shown(session_on: bool, reported_lamp_on: bool) -> bool:
    """The lamp entity is off for the whole time the power switch is off."""
    return bool(session_on and reported_lamp_on)


def session_actions(turn_on: bool, *, drawing: bool) -> tuple[str, ...]:
    """Commands for the integration power switch.

    Drifted's ``0x14/16`` is not a real power-off on this table, so it is not
    in the list. Off pauses a drawing ball and turns the lamp off. On restores
    the lamp and resumes play when the ball is idle.
    """
    if turn_on:
        if drawing:
            return ("light_on",)
        return ("light_on", "resume")
    if drawing:
        return ("pause", "light_off")
    return ("light_off",)


def project_session(
    session_on: bool,
    *,
    settled: bool,
    reported_power: bool | None,
    drawing: bool,
    reported_lamp: bool,
) -> tuple[bool, str, bool]:
    """Switch, player, and lamp after one status packet.

    ``reported_power`` is the table's ``powerOn`` byte. It is ignored. A packet
    that still says power is on, or that pauses and then draws again, cannot
    move the switch or light the player back up while the switch is off.
    """
    del reported_power
    return (
        session_on,
        shown_playback(session_on, drawing, settled=settled),
        lamp_shown(session_on, reported_lamp) and settled,
    )


@dataclass(slots=True)
class PowerQueue:
    """Collapse rapid switch presses to the latest integration state.

    One worker performs that state, so a burst cannot interleave pause and play.
    """

    pending: bool | None = None

    def push(self, on: bool) -> None:
        self.pending = bool(on)

    def pop(self) -> bool | None:
        value = self.pending
        self.pending = None
        return value


def draw_pattern(pattern_id: int) -> Packet:
    writer = _packet(CMD_ACTION, 1)
    writer.u16(pattern_id)
    return _finish(CMD_ACTION, writer)


def draw_playlist(playlist_id: str, pattern_id: int) -> Packet:
    """Start ``pattern_id`` from the playlist identified by ``playlist_id``."""
    writer = _packet(CMD_ACTION, 2)
    writer.text(playlist_id)
    writer.u16(pattern_id)
    return _finish(CMD_ACTION, writer)


def random_mode(on: bool) -> Packet:
    writer = _packet(CMD_ACTION, 10)
    writer.boolean(on)
    return _finish(CMD_ACTION, writer)


def loop_mode(on: bool) -> Packet:
    writer = _packet(CMD_ACTION, 11)
    writer.boolean(on)
    return _finish(CMD_ACTION, writer)


def start_upload(pattern_id: int, page_count: int) -> Packet:
    writer = _packet(CMD_FILE, 1)
    writer.u16(pattern_id)
    writer.u32(page_count)
    return _finish(CMD_FILE, writer)


def end_upload(pattern_id: int, page_count: int) -> Packet:
    writer = _packet(CMD_FILE, 2)
    writer.u16(pattern_id)
    writer.u32(page_count)
    return _finish(CMD_FILE, writer)


def delete_patterns(pattern_ids: list[int]) -> Packet:
    writer = _packet(CMD_FILE, 3)
    writer.u16_array(pattern_ids)
    return _finish(CMD_FILE, writer)


def pattern_page(index: int, points: list[tuple[int, int]]) -> Packet:
    """One upload page. ``index`` is 1-based. Each point is ``(t, r)``."""
    if len(points) > POINTS_PER_PAGE:
        raise ProtocolError(f"page has {len(points)} points; the maximum is {POINTS_PER_PAGE}")
    writer = _packet(CMD_PAGE, 1)
    writer.u8(len(points))
    writer.u16(index)
    for theta, radius in points:
        writer.u16(theta)
        writer.u16(radius)
    return _finish(CMD_PAGE, writer)


def reply_for(packet: Packet, moment: datetime | None = None) -> Packet | None:
    """The host reply this table packet requires.

    ConfirmData answers every table message, with two exceptions from the
    session rules: ``0x32/2`` is answered with the current time, and a packet
    that already has the ack bit is answered with ConfirmData and never in
    kind. A bare ConfirmData (the table acknowledging us) is not answered,
    or the two sides would acknowledge each other forever.
    """
    if packet.ack:
        if packet.command == CMD_CONNECTION and not packet.data:
            return None
        return confirm_data()
    if packet.command == CMD_CONNECTION and packet.action == 1:
        return confirm_connection(True)
    # 0x32/2 asks for the time. An ack-bit copy of that packet was handled above
    # and must not be answered with the time again.
    if packet.command == 0x32 and packet.action == 2:
        return current_time(moment)
    return confirm_data()


@dataclass(slots=True)
class DriftState:
    """Running state from ``0x35/1``."""

    brightness: int = 0
    color_name: str = ""
    color: tuple[int, int, int] = (255, 255, 255)
    speed_raw: int = SPEED_RAW_MIN
    playlist_id: str = ""
    pattern_id: int = 0
    progress: float = 0.0
    status: int = 0
    random_mode: bool = False
    loop_mode: bool = False
    sleep: bool = False
    breathing: bool = False
    shifting: bool = False
    shift_time: int = 0
    controller_version: str = ""
    driver_version: str = ""
    power_on: bool | None = None
    lamp_on: bool = False

    @property
    def drawing(self) -> bool:
        return self.status == 1

    @property
    def playback(self) -> str:
        """``playing`` while the table reports drawing, otherwise ``paused``.

        This does not look at power. Callers must tolerate a missing state:
        Home Assistant reads media-player properties even when the entity is
        still unavailable.
        """
        if self.status == 1:
            return "playing"
        return "paused"

    @property
    def speed_percent(self) -> float:
        return speed_raw_to_percent(self.speed_raw)


def _parse_state(reader: _Reader) -> DriftState | None:
    try:
        brightness_level = reader.u8()
        color_name = reader.text()
        color = reader.rgb()
        speed = reader.u8()
        playlist_id = reader.text()
        pattern_id = reader.u16()
        progress = reader.u16()
    except ProtocolError:
        return None
    state = DriftState(
        brightness=brightness_level,
        color_name=color_name,
        color=color,
        speed_raw=speed,
        playlist_id=playlist_id,
        pattern_id=pattern_id,
        progress=progress / 10000.0,
        lamp_on=brightness_level > 0,
    )
    status = reader._optional(reader.u8)
    if status is None:
        return state
    state.status = status
    for name in ("random_mode", "loop_mode", "sleep", "breathing", "shifting"):
        value = reader._optional(reader.boolean)
        if value is None:
            return state
        setattr(state, name, value)
    shift_time = reader._optional(reader.u16)
    if shift_time is None:
        return state
    state.shift_time = shift_time
    controller = reader._optional(reader.text)
    if controller is None:
        return state
    state.controller_version = controller
    if reader._optional(reader.boolean) is None or reader._optional(reader.u8) is None:
        return state
    driver = reader._optional(reader.text)
    if driver is None:
        return state
    state.driver_version = driver
    if reader._optional(reader.boolean) is None or reader._optional(reader.u8) is None:
        return state
    power_on = reader._optional(reader.boolean)
    if power_on is not None:
        state.power_on = power_on
    return state


def is_raw_playlist_id(value: str | None) -> bool:
    """True for numeric ids such as the app's millisecond timestamps.

    Those strings are how the table addresses a playlist. They are not names.
    """
    return bool(value) and value.isdigit() and len(value) >= 8


@dataclass(frozen=True, slots=True)
class Playlist:
    """One playlist reported by the table."""

    protocol_id: str
    index: int
    name: str | None
    pattern_ids: tuple[int, ...] = ()

    @property
    def label(self) -> str:
        if self.name and not is_raw_playlist_id(self.name):
            return self.name
        return f"Playlist {self.index}"


@dataclass(frozen=True, slots=True)
class _Draft:
    name: str | None
    pattern_ids: tuple[int, ...]
    index: int | None = None
    protocol_id: str | None = None


def _read_named(reader: _Reader, count: int) -> list[_Draft]:
    drafts: list[_Draft] = []
    for _ in range(count):
        drafts.append(_Draft(name=reader.text() or None, pattern_ids=tuple(reader.u16_array())))
    return drafts


def _read_indexed(reader: _Reader, count: int) -> list[_Draft]:
    drafts: list[_Draft] = []
    for _ in range(count):
        index = reader.u16()
        name = reader.text() or None
        drafts.append(_Draft(name=name, pattern_ids=tuple(reader.u16_array()), index=index))
    return drafts


def _layouts(payload: bytes) -> list[_Draft] | None:
    """Return playlist drafts when ``payload`` matches a documented layout."""

    def attempt(parse) -> list[_Draft] | None:  # noqa: ANN001
        reader = _Reader(payload)
        try:
            drafts = parse(reader)
        except ProtocolError:
            return None
        if not reader.finished():
            return None
        return drafts

    def named(reader: _Reader) -> list[_Draft]:
        reader.u8()
        return _read_named(reader, reader.u8())

    def id_then_name(reader: _Reader) -> list[_Draft]:
        """``page, count, count × (id, name, pattern ids)``.

        The official app addresses playlists with a numeric string, often a
        millisecond timestamp, and can send the human name as the next string.
        Accept this only when the first string is that kind of id, so a normal
        name-plus-patterns page is not split in half.
        """
        reader.u8()
        count = reader.u8()
        drafts: list[_Draft] = []
        for _ in range(count):
            ident = reader.text()
            name = reader.text() or None
            if not is_raw_playlist_id(ident):
                raise ProtocolError("playlist id is not a raw id")
            if name and is_raw_playlist_id(name):
                name = None
            drafts.append(
                _Draft(name=name, pattern_ids=tuple(reader.u16_array()), protocol_id=ident)
            )
        return drafts

    def indexed(reader: _Reader) -> list[_Draft]:
        reader.u8()
        return _read_indexed(reader, reader.u8())

    def indices(reader: _Reader) -> list[_Draft]:
        reader.u8()
        return [_Draft(name=None, pattern_ids=(), index=value) for value in reader.u16_array()]

    def names(reader: _Reader) -> list[_Draft]:
        reader.u8()
        count = reader.u8()
        return [_Draft(name=reader.text() or None, pattern_ids=()) for _ in range(count)]

    for parse in (id_then_name, named, indexed, indices, names):
        parsed = attempt(parse)
        if parsed is not None:
            return parsed
    return None


class Kind(StrEnum):
    """Coarse type of a table message."""

    WAITING = "waiting"
    CONFIRM = "confirm"
    INIT_COMPLETE = "init_complete"
    REQUESTS_TIME = "requests_time"
    STATE = "state"
    PLAYLIST = "playlist"
    LIGHT_MODE = "light_mode"
    PLAYLIST_RESET = "playlist_reset"
    UPLOAD_MISSING = "upload_missing"
    UPLOAD_STARTED = "upload_started"
    UPLOAD_STORED = "upload_stored"
    UPLOAD_FAILED = "upload_failed"
    DELETE_COMPLETE = "delete_complete"
    NO_STORAGE = "no_storage"
    ALARM = "alarm"
    PATTERNS = "patterns"
    PATTERNS_START = "patterns_start"
    PATTERNS_END = "patterns_end"
    OTHER = "other"


@dataclass(slots=True)
class Message:
    """A decoded table packet."""

    kind: Kind
    packet: Packet
    state: DriftState | None = None
    pages: list[int] | None = None
    pattern_id: int | None = None
    pattern_ids: list[int] | None = None
    alarm_kind: int | None = None
    alarm_codes: list[int] | None = None
    playlists: list[Playlist] | None = None
    light_shifting: bool | None = None
    light_shift_time: int | None = None
    light_breathing: bool | None = None
    light_brightness: int | None = None

    @property
    def upload_succeeded(self) -> bool:
        """True only for ``0x34/3``. An empty missing-page list is not success."""
        return self.kind is Kind.UPLOAD_STORED


def decode(packet: Packet, *, next_playlist_index: int = 1) -> Message:
    """Decode one table packet."""
    command, action = packet.command, packet.action
    if command == CMD_CONNECTION and action == 1:
        return Message(Kind.WAITING, packet)
    if command == CMD_CONNECTION and not packet.data:
        return Message(Kind.CONFIRM, packet)
    if command == CMD_INIT and action == 1:
        return Message(Kind.INIT_COMPLETE, packet)
    if command == 0x32 and action == 2:
        return Message(Kind.REQUESTS_TIME, packet)
    if command == 0x31 and action == 4:
        parsed = parse_light_mode_echo(packet.arguments)
        if parsed is None:
            return Message(Kind.OTHER, packet)
        shifting, shift_time, breathing, level = parsed
        return Message(
            Kind.LIGHT_MODE,
            packet,
            light_shifting=shifting,
            light_shift_time=shift_time,
            light_breathing=breathing,
            light_brightness=level,
        )
    if command == CMD_STATE and action == 1:
        state = _parse_state(_Reader(packet.arguments))
        if state is None:
            return Message(Kind.OTHER, packet)
        return Message(Kind.STATE, packet, state=state)
    if command == CMD_PLAYLIST_LIST:
        return _decode_playlist(packet, next_playlist_index)
    if command == CMD_UPLOAD:
        return _decode_upload(packet)
    if command == CMD_ALARM and action in (1, 2, 3):
        try:
            codes = _Reader(packet.arguments).u16_array()
        except ProtocolError:
            return Message(Kind.OTHER, packet)
        return Message(Kind.ALARM, packet, alarm_kind=action, alarm_codes=codes)
    if command == CMD_PATTERNS and action == 1:
        return Message(Kind.PATTERNS_START, packet)
    if command == CMD_PATTERNS and action == 2:
        return Message(Kind.PATTERNS_END, packet)
    if command == CMD_PATTERNS and action == 3:
        reader = _Reader(packet.arguments)
        try:
            reader.u8()
            return Message(Kind.PATTERNS, packet, pattern_ids=reader.u16_array())
        except ProtocolError:
            return Message(Kind.OTHER, packet)
    return Message(Kind.OTHER, packet)


def _decode_upload(packet: Packet) -> Message:
    reader = _Reader(packet.arguments)
    try:
        if packet.action == 1:
            return Message(Kind.UPLOAD_MISSING, packet, pages=reader.u16_array())
        if packet.action in (2, 3, 4, 5, 6):
            pattern_id = reader.u16()
            kind = {
                2: Kind.UPLOAD_STARTED,
                3: Kind.UPLOAD_STORED,
                4: Kind.DELETE_COMPLETE,
                5: Kind.UPLOAD_FAILED,
                6: Kind.NO_STORAGE,
            }.get(packet.action, Kind.OTHER)
            return Message(kind, packet, pattern_id=pattern_id)
    except ProtocolError:
        return Message(Kind.OTHER, packet)
    return Message(Kind.OTHER, packet)


def _decode_playlist(packet: Packet, next_index: int) -> Message:
    if packet.action not in (1, 2, 3, 4):
        return Message(Kind.OTHER, packet)
    drafts = _layouts(packet.arguments)
    if drafts is None:
        if packet.action == 1 and len(packet.arguments) <= 4:
            return Message(Kind.PLAYLIST_RESET, packet, playlists=[])
        return Message(Kind.OTHER, packet)
    playlists: list[Playlist] = []
    index = next_index
    for draft in drafts:
        use_index = draft.index if draft.index is not None else index
        name = draft.name or None
        if name and is_raw_playlist_id(name):
            protocol_id = draft.protocol_id or name
            name = None
        elif draft.protocol_id:
            protocol_id = draft.protocol_id
        else:
            protocol_id = name if name else str(use_index)
        playlists.append(
            Playlist(
                protocol_id=protocol_id,
                index=use_index,
                name=name,
                pattern_ids=draft.pattern_ids,
            )
        )
        index = max(index, use_index) + 1
    return Message(Kind.PLAYLIST, packet, playlists=playlists)


@dataclass(slots=True)
class PlaylistCatalogue:
    """Playlists collected from the table since the handshake restarted."""

    playlists: list[Playlist] = field(default_factory=list)

    def clear(self) -> None:
        self.playlists.clear()

    def apply(self, message: Message) -> bool:
        """Merge one decoded message. Return True when the catalogue changed."""
        if message.kind is Kind.PLAYLIST_RESET:
            changed = bool(self.playlists)
            self.playlists.clear()
            return changed
        if message.kind is not Kind.PLAYLIST or not message.playlists:
            return False
        changed = False
        for playlist in message.playlists:
            for position, current in enumerate(self.playlists):
                if current.protocol_id == playlist.protocol_id:
                    if current != playlist:
                        self.playlists[position] = playlist
                        changed = True
                    break
            else:
                self.playlists.append(playlist)
                changed = True
        return changed

    def options(self) -> list[tuple[str, Playlist]]:
        """Unique labels paired with the playlist they select."""
        counts: dict[str, int] = {}
        for playlist in self.playlists:
            counts[playlist.label] = counts.get(playlist.label, 0) + 1
        seen: dict[str, int] = {}
        labeled: list[tuple[str, Playlist]] = []
        for playlist in self.playlists:
            base = playlist.label
            if counts[base] == 1:
                label = base
            else:
                seen[base] = seen.get(base, 0) + 1
                label = f"{base} ({seen[base]})"
            labeled.append((label, playlist))
        return labeled

    def label_for(self, protocol_id: str) -> str | None:
        if not protocol_id:
            return None
        for label, playlist in self.options():
            if playlist.protocol_id == protocol_id:
                return label
        return None

    def by_label(self, label: str) -> Playlist | None:
        for option, playlist in self.options():
            if option == label:
                return playlist
        return None

    def playlist_for(self, protocol_id: str) -> Playlist | None:
        """The playlist whose wire id matches the running state."""
        if not protocol_id:
            return None
        for playlist in self.playlists:
            if playlist.protocol_id == protocol_id:
                return playlist
        return None

    def ingest(self, packet: Packet) -> Message:
        """Decode ``packet``, refreshing playlists when the table sends them.

        A new handshake (``0x50/1``) drops the previous catalogue so the list
        is exactly what this connection reports.
        """
        next_index = max((item.index for item in self.playlists), default=0) + 1
        message = decode(packet, next_playlist_index=next_index)
        if message.kind is Kind.WAITING:
            self.clear()
        else:
            self.apply(message)
        return message


def pattern_label(pattern_id: int) -> str:
    """Label for a stored pattern.

    The table's pattern list (``0x33``) is ids only. Drifted keeps human names
    on the computer that uploaded a drawing, not on the table, so a pattern
    the table knows is shown as ``Pattern N``.
    """
    return f"Pattern {int(pattern_id)}"


def playlist_pattern_index(pattern_ids: tuple[int, ...] | list[int], pattern_id: int) -> int | None:
    """1-based position of ``pattern_id`` in a playlist, when that playlist lists it."""
    try:
        return tuple(pattern_ids).index(pattern_id) + 1
    except ValueError:
        return None


@dataclass(slots=True)
class PatternCatalogue:
    """Pattern ids the table listed with ``0x33``.

    The handshake dumps them, and the table sends the list again after an
    upload or delete. Nothing is requested on a timer. A start (``0x33/1``)
    begins a fresh dump; pages (``0x33/3``) add ids; an end with no pages
    means the table stored nothing. Id 0 is the idle placeholder and is not
    offered as a pattern to play.
    """

    pattern_ids: tuple[int, ...] = ()
    _reset_pending: bool = False

    def clear(self) -> None:
        self.pattern_ids = ()
        self._reset_pending = False

    def note(self, message: Message) -> bool:
        """Merge one decoded message. Return True when the stored ids changed."""
        if message.kind is Kind.WAITING:
            changed = bool(self.pattern_ids)
            self.clear()
            return changed
        if message.kind is Kind.PATTERNS_START:
            self._reset_pending = True
            return False
        if message.kind is Kind.PATTERNS_END:
            if not self._reset_pending:
                return False
            changed = bool(self.pattern_ids)
            self.pattern_ids = ()
            self._reset_pending = False
            return changed
        if message.kind is not Kind.PATTERNS:
            return False
        incoming = message.pattern_ids or []
        if self._reset_pending:
            merged = tuple(incoming)
            self._reset_pending = False
        else:
            merged = (*self.pattern_ids, *incoming)
        ordered = tuple(sorted({pattern_id for pattern_id in merged if pattern_id}))
        if ordered == self.pattern_ids:
            return False
        self.pattern_ids = ordered
        return True

    def options(self) -> list[tuple[str, int]]:
        """Labels in id order. The table does not send a separate name."""
        return [(pattern_label(pattern_id), pattern_id) for pattern_id in self.pattern_ids]

    def names(self) -> list[str]:
        return [label for label, _pattern_id in self.options()]

    def by_label(self, label: str) -> int | None:
        for option, pattern_id in self.options():
            if option == label:
                return pattern_id
        return None

    def label_for(self, pattern_id: int) -> str | None:
        """``Pattern N`` when the table has reported that id. Idle (0) is unnamed."""
        if pattern_id <= 0:
            return None
        for option, stored in self.options():
            if stored == pattern_id:
                return option
        return pattern_label(pattern_id)


def normalize_advertised_name(name: str | None) -> str:
    """Trim the trailing CR/LF the tables sometimes leave on the local name."""
    if not name:
        return ""
    return name.replace("\r", "").replace("\n", "").strip()


def is_drift_name(name: str | None) -> bool:
    """True for a trimmed local name of 12 or more characters starting with KS."""
    cleaned = normalize_advertised_name(name)
    return len(cleaned) >= 12 and cleaned.startswith("KS")


def alarm_text(codes: list[int]) -> str:
    return ", ".join(f"{code} {ALARM_NAMES.get(code, 'unknown')}" for code in codes)
