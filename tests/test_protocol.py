"""Packet encode/decode tests against Drifted's published vectors.

The fixture is ``spec/vectors/protocol.json`` from Josh Lannin's Drifted
project (https://github.com/joshlannin/drifted, MIT). Drifted
reverse-engineered the bytes. This Home Assistant integration was converted
from Drifted using Grok Bot.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.homedics_drift.protocol import (
    CMD_FIRMWARE,
    Packet,
    PacketParser,
    PatternCatalogue,
    PlaylistCatalogue,
    alarm_text,
    brightness,
    confirm_connection,
    confirm_data,
    current_time,
    decode,
    delete_patterns,
    draw_pattern,
    draw_playlist,
    end_upload,
    fixed_color,
    is_drift_name,
    is_raw_playlist_id,
    LampHold,
    lamp_on_packets,
    light_mode,
    parse_light_mode_echo,
    reconcile_lamp,
    PowerQueue,
    playback_allowed,
    player_controls,
    project_session,
    session_actions,
    shown_playback,
    StopAfterWatch,
    transport_action,
    normalize_advertised_name,
    resolved_lamp_level,
    pattern_label,
    pattern_page,
    playlist_pattern_index,
    percent_to_speed_raw,
    next_pattern,
    play_pause,
    power,
    previous_pattern,
    random_mode,
    reply_for,
    select_color,
    show_color,
    speed_percent,
    start_upload,
    Kind,
    DriftState,
)

FIXTURE = Path(__file__).parent / "fixtures" / "protocol.json"
VECTORS = json.loads(FIXTURE.read_text())
# Sunday 2026-10-25 13:45:30, the timestamp baked into the time vector.
FIXED_TIME = datetime(2026, 10, 25, 13, 45, 30)


def _unhex(text: str) -> bytes:
    return bytes.fromhex(text)


def _hex(data: bytes) -> str:
    return data.hex(" ")


def _parse_one(text: str) -> Packet:
    parser = PacketParser()
    packets = parser.feed(_unhex(text))
    assert len(packets) == 1
    assert parser.checksum_failures == 0
    return packets[0]


def _circle() -> list[tuple[int, int]]:
    return [((index * 60000 // 40) % 60000, 25000) for index in range(41)]


def _host_packet(name: str) -> Packet:
    circle = _circle()
    builders = {
        "confirm_data": confirm_data,
        "confirm_connection": lambda: confirm_connection(True),
        "current_time": lambda: current_time(FIXED_TIME),
        "draw_pattern_50000": lambda: draw_pattern(50000),
        "play_pause": play_pause,
        "speed_max": lambda: speed_percent(100),
        "brightness_100": lambda: brightness(100),
        "random_off": lambda: random_mode(False),
        "color_white_store_temp": lambda: show_color(255, 255, 255),
        "select_color_temp": lambda: select_color("Temp"),
        "light_fixed_full": lambda: light_mode(
            shifting=False, shift_time=0, breathing=False, brightness_level=100
        ),
        "start_upload_50000_2_pages": lambda: start_upload(50000, 2),
        "page_1": lambda: pattern_page(1, circle[:40]),
        "page_2": lambda: pattern_page(2, circle[40:]),
        "end_upload_50000_2_pages": lambda: end_upload(50000, 2),
        "delete_50000": lambda: delete_patterns([50000]),
    }
    return builders[name]()


def test_fixture_covers_every_host_vector() -> None:
    names = [entry["name"] for entry in VECTORS["host_to_table"]]
    assert names == [
        "confirm_data",
        "confirm_connection",
        "current_time",
        "draw_pattern_50000",
        "play_pause",
        "speed_max",
        "brightness_100",
        "random_off",
        "color_white_store_temp",
        "select_color_temp",
        "light_fixed_full",
        "start_upload_50000_2_pages",
        "page_1",
        "page_2",
        "end_upload_50000_2_pages",
        "delete_50000",
    ]


@pytest.mark.parametrize("entry", VECTORS["host_to_table"], ids=lambda entry: entry["name"])
def test_host_vectors_encode(entry: dict) -> None:
    assert _hex(_host_packet(entry["name"]).encode()) == entry["hex"]


def test_fixed_color_recipe_matches_vectors() -> None:
    packets = fixed_color(255, 255, 255, 100)
    encoded = [_hex(packet.encode()) for packet in packets]
    by_name = {entry["name"]: entry["hex"] for entry in VECTORS["host_to_table"]}
    assert encoded == [
        by_name["color_white_store_temp"],
        by_name["select_color_temp"],
        by_name["light_fixed_full"],
    ]
    # The enable byte sits in front of RGB. Without it, white is sent as yellow.
    raw = packets[0].encode()
    assert raw[3:8] == bytes((0x0F, 0x01, 0xFF, 0xFF, 0xFF))


@pytest.mark.parametrize("entry", VECTORS["table_to_host"], ids=lambda entry: entry["name"])
def test_table_vectors_parse(entry: dict) -> None:
    packet = _parse_one(entry["hex"])
    catalogue = PlaylistCatalogue()
    message = catalogue.ingest(packet)
    decoded = entry.get("decoded")
    if entry["name"] == "running_state":
        assert message.kind is Kind.STATE
        assert message.state is not None
        state = message.state
        assert state.brightness == decoded["brightness"]
        assert state.color_name == decoded["colorName"]
        assert state.color == (255, 255, 255)
        assert state.speed_raw == 0x4B
        assert state.playlist_id == ""
        assert state.pattern_id == decoded["patternId"]
        assert state.progress == pytest.approx(decoded["progress"])
        assert state.status == decoded["status"]
        assert state.random_mode is decoded["random"]
        assert state.loop_mode is decoded["loop"]
        assert state.sleep is True
        assert state.controller_version == decoded["controllerVersion"]
        assert state.driver_version == decoded["driverVersion"]
        assert state.power_on is True
    elif entry["name"] == "upload_missing_pages":
        assert message.kind is Kind.UPLOAD_MISSING
        assert message.pages == decoded["missing"]
        assert message.upload_succeeded is False
    elif entry["name"] == "upload_missing_none":
        assert message.kind is Kind.UPLOAD_MISSING
        assert message.pages == []
        assert message.upload_succeeded is False
    elif entry["name"] == "upload_stored":
        assert message.kind is Kind.UPLOAD_STORED
        assert message.pattern_id == decoded["patternId"]
        assert message.upload_succeeded is True
    elif entry["name"] == "upload_started":
        assert message.kind is Kind.UPLOAD_STARTED
        assert message.pattern_id == decoded["patternId"]
        assert packet.ack is True
    elif entry["name"] == "upload_failed":
        assert message.kind is Kind.UPLOAD_FAILED
        assert message.pattern_id == decoded["patternId"]
        assert message.upload_succeeded is False
    elif entry["name"] == "alarm_fatal_10_13":
        assert message.kind is Kind.ALARM
        assert message.alarm_kind == decoded["kind"]
        assert message.alarm_codes == decoded["codes"]
        assert "can't open pattern file" in alarm_text(message.alarm_codes or [])
    elif entry["name"] == "waiting_for_confirm":
        assert message.kind is Kind.WAITING
    elif entry["name"] == "asks_for_time":
        assert message.kind is Kind.REQUESTS_TIME
    elif entry["name"] == "ack_of_time":
        assert packet.ack is True
        assert packet.command == 0x32
    elif entry["name"] == "init_complete":
        assert message.kind is Kind.INIT_COMPLETE


def test_handshake_replies_match_the_exchange() -> None:
    handshake = next(item for item in VECTORS["exchanges"] if item["name"] == "handshake")
    steps = handshake["steps"]
    index = 0
    while index < len(steps):
        step = steps[index]
        if step["from"] != "table":
            index += 1
            continue
        reply = reply_for(_parse_one(step["hex"]), FIXED_TIME)
        assert reply is not None
        index += 1
        assert steps[index]["from"] == "host"
        assert _hex(reply.encode()) == steps[index]["hex"]
        index += 1


def test_ack_of_time_is_not_answered_with_the_time() -> None:
    packet = _parse_one(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "ack_of_time"))
    reply = reply_for(packet, FIXED_TIME)
    assert reply is not None
    assert reply.encode() == confirm_data().encode()
    assert reply.encode() != current_time(FIXED_TIME).encode()


def test_bare_confirm_data_is_not_answered() -> None:
    packet = Packet(0x50, b"", ack=True)
    assert reply_for(packet, FIXED_TIME) is None


def test_parser_reassembles_split_and_joined_packets() -> None:
    stored = _unhex(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "upload_stored"))
    init = _unhex(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "init_complete"))
    parser = PacketParser()
    assert parser.feed(b"\x00" + stored[:3]) == []
    packets = parser.feed(stored[3:] + init)
    assert [(packet.command, packet.ack, packet.data) for packet in packets] == [
        (0x34, True, bytes((0x03, 0x50, 0xC3))),
        (0x4F, False, bytes((0x01,))),
    ]
    assert parser.dropped_bytes == 1


def test_parser_accepts_checksum_computed_without_the_ack_bit() -> None:
    raw = bytearray(Packet(0x35, bytes((0x01,))).encode())
    raw[2] |= 0x80
    body = bytearray(raw[:-1])
    body[2] &= 0x7F
    raw[-1] = sum(body) & 0xFF
    parser = PacketParser()
    packets = parser.feed(raw)
    assert len(packets) == 1
    assert packets[0].ack is True
    assert packets[0].command == 0x35


def test_parser_rejects_a_bad_checksum_and_resynchronises() -> None:
    good = confirm_data().encode()
    broken = bytearray(good)
    broken[-1] ^= 0xFF
    parser = PacketParser()
    packets = parser.feed(bytes(broken) + good)
    assert [packet.encode() for packet in packets] == [good]
    assert parser.checksum_failures == 1


def test_full_page_is_one_packet() -> None:
    points = [(1, 1)] * 40
    encoded = pattern_page(7, points).encode()
    assert len(encoded) == 168
    assert encoded[1] == 168


def test_speed_endpoints_match_the_documented_raw_range() -> None:
    assert percent_to_speed_raw(0) == 30
    assert percent_to_speed_raw(100) == 75
    assert speed_percent(100).encode() == _host_packet("speed_max").encode()


def test_previous_and_next_are_distinct_actions() -> None:
    assert next_pattern().data == bytes((4,))
    assert previous_pattern().data == bytes((5,))


def test_draw_playlist_layout() -> None:
    raw = draw_playlist("Relax", 7).encode()
    assert raw[0] == 0x7B
    assert raw[2] == 0x14
    assert raw[3] == 0x02
    assert raw[4:10] == b"Relax\x00"
    assert raw[10:12] == bytes((7, 0))
    assert raw[1] == len(raw)
    assert raw[-1] == sum(raw[:-1]) & 0xFF


def test_firmware_update_and_reset_are_refused() -> None:
    with pytest.raises(ValueError, match="0x15"):
        Packet(CMD_FIRMWARE, bytes((1,))).encode()
    with pytest.raises(ValueError, match="0x14/12"):
        Packet(0x14, bytes((12,))).encode()


def test_advertised_names_are_trimmed_before_matching() -> None:
    assert normalize_advertised_name("KS0123456789\r\n") == "KS0123456789"
    assert is_drift_name("KS0123456789\r\n")
    assert is_drift_name("  KS0123456789AB  ")
    assert not is_drift_name("KS012345678")
    assert not is_drift_name("XK0123456789AB")
    assert not is_drift_name(None)


def _playlist_packet(action: int, payload: bytes) -> Packet:
    return Packet(0x30, bytes((action,)) + payload)


def test_named_playlist_page_is_read_from_the_table() -> None:
    # page 0, one playlist "Calm" containing patterns 1 and 2.
    payload = bytes((0x00, 0x01, 0x43, 0x61, 0x6C, 0x6D, 0x00, 0x02, 0x01, 0x00, 0x02, 0x00))
    catalogue = PlaylistCatalogue()
    message = catalogue.ingest(_playlist_packet(3, payload))
    assert message.kind is Kind.PLAYLIST
    assert [(item.protocol_id, item.pattern_ids) for item in catalogue.playlists] == [
        ("Calm", (1, 2))
    ]
    assert catalogue.options() == [("Calm", catalogue.playlists[0])]


def test_indexed_playlist_without_a_name_uses_playlist_n() -> None:
    # page 0, index 4, empty name, pattern 9.
    payload = bytes((0x00, 0x01, 0x04, 0x00, 0x00, 0x01, 0x09, 0x00))
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, payload))
    playlist = catalogue.playlists[0]
    assert playlist.name is None
    assert playlist.index == 4
    assert playlist.protocol_id == "4"
    assert playlist.pattern_ids == (9,)
    assert catalogue.options()[0][0] == "Playlist 4"


def test_index_list_falls_back_to_playlist_n() -> None:
    # page 0 and three indices, with no names and no pattern lists.
    payload = bytes((0x00, 0x03, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00))
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, payload))
    assert [label for label, _ in catalogue.options()] == [
        "Playlist 1",
        "Playlist 2",
        "Playlist 3",
    ]
    assert [item.protocol_id for item in catalogue.playlists] == ["1", "2", "3"]


def test_playlist_dump_replaces_itself_on_the_next_handshake() -> None:
    catalogue = PlaylistCatalogue()
    first = bytes((0x00, 0x01, 0x41, 0x00, 0x00))  # page 0, count 1, name "A", no patterns
    second = bytes((0x00, 0x01, 0x42, 0x00, 0x00))
    catalogue.ingest(_playlist_packet(3, first))
    catalogue.ingest(_playlist_packet(1, b"\x02"))  # start/count header clears
    catalogue.ingest(_playlist_packet(3, second))
    assert [item.protocol_id for item in catalogue.playlists] == ["B"]

    catalogue.ingest(Packet(0x50, bytes((1,))))
    assert catalogue.playlists == []


def test_playlist_pages_accumulate_until_reset() -> None:
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, bytes((0x00, 0x01, 0x41, 0x00, 0x01, 0x0A, 0x00))))
    catalogue.ingest(_playlist_packet(3, bytes((0x01, 0x01, 0x42, 0x00, 0x01, 0x0B, 0x00))))
    assert [item.protocol_id for item in catalogue.playlists] == ["A", "B"]
    assert catalogue.by_label("A").pattern_ids == (10,)  # type: ignore[union-attr]
    assert catalogue.by_label("B").pattern_ids == (11,)  # type: ignore[union-attr]


def test_same_protocol_id_updates_in_place() -> None:
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, bytes((0x00, 0x01, 0x41, 0x00, 0x00))))
    catalogue.ingest(_playlist_packet(3, bytes((0x00, 0x01, 0x41, 0x00, 0x01, 0x05, 0x00))))
    assert len(catalogue.playlists) == 1
    assert catalogue.playlists[0].pattern_ids == (5,)


def test_identical_labels_with_different_ids_stay_selectable() -> None:
    catalogue = PlaylistCatalogue()
    # A named playlist whose name is the fallback label, plus index 4 with no name.
    named = bytes((0x00, 0x01)) + b"Playlist 4\x00" + bytes((0x00,))
    indexed = bytes((0x00, 0x01, 0x04, 0x00, 0x00, 0x00))
    catalogue.ingest(_playlist_packet(3, named))
    catalogue.ingest(_playlist_packet(3, indexed))
    labels = [label for label, _playlist in catalogue.options()]
    assert labels == ["Playlist 4 (1)", "Playlist 4 (2)"]
    assert catalogue.by_label("Playlist 4 (1)").protocol_id == "Playlist 4"  # type: ignore[union-attr]
    assert catalogue.by_label("Playlist 4 (2)").protocol_id == "4"  # type: ignore[union-attr]


def test_garbage_playlist_payload_does_not_invent_entries() -> None:
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, b"\xff\xff\xff"))
    assert catalogue.playlists == []


def test_turning_the_lamp_on_restores_colour_and_nonzero_brightness() -> None:
    assert resolved_lamp_level(None, remembered=0) == 100
    assert resolved_lamp_level(0, remembered=40) == 40
    assert resolved_lamp_level(80, remembered=40) == 80

    packets = lamp_on_packets(
        level=resolved_lamp_level(None, remembered=0),
        color=(255, 255, 255),
        color_name="Temp",
        shifting=True,
        shift_time=9,
        breathing=True,
        from_off=True,
    )
    assert [packet.data[0] for packet in packets] == [0x0F, 13, 4, 7]
    show, select, mode, live = packets
    assert show.data[:2] == bytes((0x0F, 0x01))
    assert show.data[2:5] == bytes((255, 255, 255))
    assert b"Temp\x00" in select.data
    assert mode.data[0] == 4
    assert mode.data[-1] == 100
    assert live.data == bytes((7, 100))
    assert all(packet.data[-1] != 0 for packet in (mode, live))


def test_brightness_change_while_on_uses_light_mode() -> None:
    packets = lamp_on_packets(
        level=40,
        color=(1, 2, 3),
        color_name="c0",
        shifting=True,
        shift_time=12,
        breathing=False,
        from_off=False,
    )
    assert [packet.data for packet in packets] == [
        bytes((4, 1, 12, 0, 0, 40)),
        bytes((7, 40)),
    ]


def test_named_palette_colour_is_reselected_when_the_lamp_comes_on() -> None:
    packets = lamp_on_packets(
        level=55,
        color=(9, 8, 7),
        color_name="c0",
        shifting=True,
        shift_time=4,
        breathing=False,
        from_off=True,
    )
    assert [packet.data[0] for packet in packets] == [0x0F, 13, 4, 7]
    assert packets[0].data[1] == 1
    assert packets[0].data[2:5] == bytes((9, 8, 7))
    assert b"Temp\x00" in packets[1].data
    assert packets[2].data[-1] == 55
    assert packets[3].data == bytes((7, 55))


def _nul(text: str) -> bytes:
    return text.encode("ascii") + b"\x00"


def test_table_power_byte_is_not_the_switch() -> None:
    # 0x14/16 exists, but the switch does not send it. Value 0 is not real off.
    assert power(False).data == bytes((16, 0))
    assert "table_power" not in session_actions(False, drawing=True)
    assert session_actions(False, drawing=True) == ("pause", "light_off")
    assert session_actions(False, drawing=False) == ("light_off",)
    assert session_actions(True, drawing=False) == ("light_on", "resume")
    assert session_actions(True, drawing=True) == ("light_on",)


def test_status_packets_cannot_bounce_power_back_on() -> None:
    # What the table did: powerOn stayed true, playback paused, then ran again.
    reports = (
        (True, True, True),
        (True, False, True),
        (True, True, True),
        (True, False, False),
    )
    for reported_power, drawing, reported_lamp in reports:
        switch, player, lamp = project_session(
            False,
            settled=True,
            reported_power=reported_power,
            drawing=drawing,
            reported_lamp=reported_lamp,
        )
        assert switch is False
        assert player == "off"
        assert lamp is False
    # During the command the same packets still cannot flip the switch or player.
    switch, player, lamp = project_session(
        False,
        settled=False,
        reported_power=True,
        drawing=False,
        reported_lamp=True,
    )
    assert (switch, player, lamp) == (False, "off", False)


def test_rapid_power_flips_collapse_to_the_last_request() -> None:
    queue = PowerQueue()
    queue.push(False)
    queue.push(True)
    queue.push(False)
    assert queue.pop() is False
    assert queue.pop() is None


def test_pause_does_not_change_power_and_play_does_not_turn_it_on() -> None:
    assert transport_action("pause", True, drawing=True) == (True, "pause")
    assert transport_action("pause", True, drawing=False) == (True, None)
    assert transport_action("pause", False, drawing=True) == (False, None)
    assert transport_action("play", False, drawing=False) == (False, None)
    assert transport_action("play", False, drawing=True) == (False, None)
    assert transport_action("play", True, drawing=False) == (True, "resume")
    assert transport_action("play", True, drawing=True) == (True, None)
    # Only the power switch changes power.
    assert transport_action("power_off", True, drawing=True) == (False, "session_off")
    assert transport_action("power_on", False, drawing=False) == (True, "session_on")
    assert playback_allowed(False) is False
    assert playback_allowed(True) is True


def test_stop_after_pauses_at_the_end_without_touching_power() -> None:
    watch = StopAfterWatch()
    watch.enabled = True
    assert watch.observe(session_on=True, drawing=True, progress=0.4, pattern_id=3) is False
    assert watch.observe(session_on=True, drawing=True, progress=1.0, pattern_id=3) is True
    assert watch.observe(session_on=True, drawing=True, progress=1.0, pattern_id=3) is False
    assert watch.observe(session_on=False, drawing=True, progress=1.0, pattern_id=3) is False
    watch.enabled = True
    watch.pattern_id = 3
    watch.pausing = False
    assert watch.observe(session_on=True, drawing=True, progress=0.2, pattern_id=8) is True
    watch.authorize()
    assert watch.observe(session_on=True, drawing=True, progress=0.1, pattern_id=9) is False
    assert watch.observe(session_on=True, drawing=True, progress=1.0, pattern_id=9) is False
    assert watch.observe(session_on=True, drawing=True, progress=0.2, pattern_id=9) is False
    assert watch.observe(session_on=True, drawing=True, progress=1.0, pattern_id=9) is True
    assert watch.observe(session_on=True, drawing=False, progress=1.0, pattern_id=9) is False


def test_player_hides_every_transport_control_while_power_is_off() -> None:
    hidden = player_controls(False)
    assert hidden == frozenset()
    for name in ("play", "pause", "next", "previous", "turn_on", "select_source"):
        assert name not in hidden
    assert shown_playback(False, True) == "off"
    assert shown_playback(False, False, settled=False) == "off"
    shown = player_controls(True)
    assert shown == frozenset({"play", "pause", "next", "previous"})
    assert "turn_on" not in shown
    assert "select_source" not in shown
    assert shown_playback(True, True) == "playing"
    assert shown_playback(True, False) == "paused"


def test_playback_comes_from_drawing_status_without_requiring_power() -> None:
    drawing = DriftState(status=1, power_on=True, pattern_id=12, playlist_id="1666040602046")
    idle = DriftState(status=0, power_on=False, pattern_id=0, playlist_id="")
    assert drawing.playback == "playing"
    assert idle.playback == "paused"
    # A missing power flag must not be treated as "no player".
    assert DriftState(status=1, power_on=None).playback == "playing"


def test_stale_on_status_does_not_undo_lamp_off() -> None:
    off = LampHold(on=False, level=0)
    level, lamp_on, hold = reconcile_lamp(80, off)
    assert (level, lamp_on, hold) == (0, False, off)
    level, lamp_on, hold = reconcile_lamp(0, off)
    assert (level, lamp_on, hold) == (0, False, None)


def test_stale_off_status_does_not_undo_lamp_on() -> None:
    on = LampHold(on=True, level=100)
    level, lamp_on, hold = reconcile_lamp(0, on)
    assert (level, lamp_on, hold) == (100, True, on)
    level, lamp_on, hold = reconcile_lamp(90, on)
    assert (level, lamp_on, hold) == (90, True, None)


def test_uncommanded_brightness_zero_is_off() -> None:
    assert reconcile_lamp(0, None) == (0, False, None)
    assert reconcile_lamp(40, None) == (40, True, None)


def test_light_mode_echo_brightness_zero_is_off() -> None:
    # 0x31/4: shifting off, shift time 0, breathing off, brightness 0.
    packet = Packet(0x31, bytes((4, 0, 0, 0, 0, 0)))
    message = PlaylistCatalogue().ingest(packet)
    assert message.kind is Kind.LIGHT_MODE
    assert message.light_brightness == 0
    assert message.light_shifting is False
    assert parse_light_mode_echo(packet.arguments) == (False, 0, False, 0)
    assert reconcile_lamp(message.light_brightness or 0, None)[1] is False


def test_running_state_brightness_zero_means_lamp_off() -> None:
    # Same shape as the published running-state vector, with brightness forced to 0.
    raw = bytearray(_unhex(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "running_state")))
    raw[4] = 0
    raw[-1] = sum(raw[:-1]) & 0xFF
    message = PlaylistCatalogue().ingest(PacketParser().feed(bytes(raw))[0])
    assert message.state is not None
    assert message.state.brightness == 0
    assert message.state.lamp_on is False


def test_timestamp_playlist_ids_are_not_shown_as_names() -> None:
    stamp = "1666040602046"
    assert is_raw_playlist_id(stamp)
    # Id only, then an empty pattern list. The string is the wire id.
    payload = bytes((0x00, 0x01)) + _nul(stamp) + bytes((0x00,))
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, payload))
    playlist = catalogue.playlists[0]
    assert playlist.protocol_id == stamp
    assert playlist.label == "Playlist 1"
    assert catalogue.options()[0][0] == "Playlist 1"
    assert stamp not in catalogue.options()[0][0]
    assert catalogue.label_for(stamp) == "Playlist 1"


def test_playlist_timestamp_id_keeps_a_separate_name() -> None:
    stamp = "1666040602046"
    payload = bytes((0x00, 0x01)) + _nul(stamp) + _nul("Evening") + bytes((0x01, 0x07, 0x00))
    catalogue = PlaylistCatalogue()
    catalogue.ingest(_playlist_packet(3, payload))
    playlist = catalogue.playlists[0]
    assert playlist.protocol_id == stamp
    assert playlist.name == "Evening"
    assert playlist.label == "Evening"
    assert playlist.pattern_ids == (7,)
    assert catalogue.label_for(stamp) == "Evening"
    assert stamp not in {label for label, _item in catalogue.options()}


def _pattern_packet(action: int, payload: bytes = b"") -> Packet:
    return Packet(0x33, bytes((action,)) + payload)


def test_stored_patterns_are_ids_labeled_pattern_n() -> None:
    catalogue = PatternCatalogue()
    assert catalogue.note(decode(_pattern_packet(1))) is False
    page = bytes((0x00, 0x03, 0x02, 0x00, 0x01, 0x00, 0x0A, 0x00))
    assert catalogue.note(decode(_pattern_packet(3, page))) is True
    assert catalogue.note(decode(_pattern_packet(3, bytes((0x01, 0x01, 0x00, 0x00))))) is False
    assert catalogue.pattern_ids == (1, 2, 10)
    assert catalogue.names() == ["Pattern 1", "Pattern 2", "Pattern 10"]
    assert catalogue.by_label("Pattern 2") == 2
    assert catalogue.label_for(2) == "Pattern 2"
    assert catalogue.label_for(0) is None
    assert pattern_label(834) == "Pattern 834"
    assert catalogue.note(decode(_pattern_packet(2))) is False


def test_pattern_dump_replaces_the_previous_list() -> None:
    catalogue = PatternCatalogue()
    catalogue.note(decode(_pattern_packet(3, bytes((0x00, 0x01, 0x05, 0x00)))))
    catalogue.note(decode(_pattern_packet(1)))
    catalogue.note(decode(_pattern_packet(3, bytes((0x00, 0x01, 0x09, 0x00)))))
    assert catalogue.names() == ["Pattern 9"]
    catalogue.note(decode(_pattern_packet(1)))
    assert catalogue.note(decode(_pattern_packet(2))) is True
    assert catalogue.names() == []


def test_new_handshake_clears_stored_patterns() -> None:
    catalogue = PatternCatalogue()
    catalogue.note(decode(_pattern_packet(3, bytes((0x00, 0x01, 0x04, 0x00)))))
    waiting = decode(Packet(0x50, bytes((1,))))
    assert catalogue.note(waiting) is True
    assert catalogue.names() == []


def test_playlist_pattern_index_is_one_based() -> None:
    assert playlist_pattern_index((4, 9, 12), 9) == 2
    assert playlist_pattern_index((4, 9), 3) is None


def test_upload_stored_is_the_only_success_signal() -> None:
    missing = PlaylistCatalogue().ingest(
        _parse_one(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "upload_missing_none"))
    )
    stored = PlaylistCatalogue().ingest(
        _parse_one(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "upload_stored"))
    )
    failed = PlaylistCatalogue().ingest(
        _parse_one(next(item["hex"] for item in VECTORS["table_to_host"] if item["name"] == "upload_failed"))
    )
    assert missing.upload_succeeded is False
    assert stored.upload_succeeded is True
    assert failed.upload_succeeded is False
