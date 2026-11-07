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
    PlaylistCatalogue,
    alarm_text,
    brightness,
    confirm_connection,
    confirm_data,
    current_time,
    delete_patterns,
    draw_pattern,
    draw_playlist,
    end_upload,
    fixed_color,
    is_drift_name,
    light_mode,
    normalize_advertised_name,
    pattern_page,
    percent_to_speed_raw,
    next_pattern,
    play_pause,
    previous_pattern,
    random_mode,
    reply_for,
    select_color,
    show_color,
    speed_percent,
    start_upload,
    Kind,
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
