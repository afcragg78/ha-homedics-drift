"""Pattern upload planning. No table and no Home Assistant."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from custom_components.homedics_drift.patterns import (
    STORAGE_CAP,
    USER_ID_MIN,
    PatternLibrary,
    PatternRejected,
    allocate_id,
    deletion_refusal,
    densify,
    inbox_names,
    label_patterns,
    paginate,
    parse_thr,
    path_under_config,
    resend_indexes,
    slots,
    thr_to_wire,
    wire_point,
)


def test_sandify_thr_becomes_drifted_wire_points() -> None:
    assert parse_thr("# comment\n\n0 1\n") == [(0.0, 1.0)]
    assert wire_point(0.0, 1.0) == (0, 50000)
    assert wire_point(math.pi, 0.5) == (30000, 25000)
    wire = thr_to_wire("0,1\n0,0.5\n")
    assert wire[0] == (0, 50000)
    assert wire[-1][1] == 25000
    assert len(wire) >= 2


def test_pages_hold_forty_points_except_the_last() -> None:
    points = [(index, 1) for index in range(41)]
    pages = paginate(points)
    assert [len(page) for page in pages] == [40, 1]
    assert paginate(points[:40]) == [points[:40]]


def test_empty_missing_list_resends_a_growing_tail() -> None:
    assert resend_indexes(5, [], 1) == [2, 3, 4]
    assert resend_indexes(5, [], 2) == [0, 1, 2, 3, 4]
    assert resend_indexes(5, [1, 3], 1) == [0, 2]


def test_new_ids_start_at_50000_and_stop_at_the_cap() -> None:
    stored = {1, 2, 52}
    assert allocate_id(stored, playing=12, reuse=None) == USER_ID_MIN
    assert allocate_id(stored | {50000}, playing=50000, reuse=None) == 50001
    with pytest.raises(PatternRejected, match="came with the table"):
        allocate_id(stored, playing=None, reuse=12)
    with pytest.raises(PatternRejected, match="drawing"):
        allocate_id(stored | {50010}, playing=50010, reuse=50010)
    assert allocate_id(set(range(STORAGE_CAP)), playing=None, reuse=50000) == 50000
    with pytest.raises(PatternRejected, match="700"):
        allocate_id(set(range(STORAGE_CAP)), playing=None, reuse=None)
    used, free = slots(690)
    assert (used, free) == (690, 10)
    assert slots(700) == (700, 0)


def test_delete_refuses_stock_ids_and_the_pattern_that_is_drawing() -> None:
    uploaded = {50000, 50001}
    stored = {1, 12, 50000, 50001}
    assert deletion_refusal(12, stored=stored, playing=None, uploaded=uploaded) is not None
    assert deletion_refusal(50000, stored=stored, playing=50000, uploaded=uploaded) is not None
    assert deletion_refusal(50001, stored=set(), playing=None, uploaded=uploaded) is not None
    assert deletion_refusal(50001, stored=stored, playing=50000, uploaded=uploaded) is None
    assert deletion_refusal(60000, stored=stored | {60000}, playing=None, uploaded=uploaded) is not None


def test_names_and_inbox_stay_on_this_machine() -> None:
    library = PatternLibrary()
    library.remember(50000, "Spiral", "0 1\n", "spiral.thr")
    library.rename(12, "Calm")
    assert library.name_for(50000) == "Spiral"
    assert library.name_for(12) == "Calm"
    restored = PatternLibrary.from_dict(library.to_dict())
    assert restored.name_for(12) == "Calm"
    assert restored.records[50000].thr == "0 1\n"
    assert inbox_names(["spiral.thr", "rose.thr", "notes.txt"], library) == ["rose.thr"]
    labels = label_patterns([12, 50000], library.names())
    assert labels == [("Calm", 12), ("Spiral", 50000)]


def test_pattern_path_must_stay_inside_config() -> None:
    root = Path("/config")
    assert path_under_config(root, "/config/drift_patterns/spiral.thr") == Path(
        "/config/drift_patterns/spiral.thr"
    )
    with pytest.raises(PatternRejected):
        path_under_config(root, "/etc/passwd")
    with pytest.raises(PatternRejected):
        path_under_config(root, "/config/drift_patterns/spiral.txt")


def test_preview_is_a_png() -> None:
    pytest.importorskip("PIL")
    from custom_components.homedics_drift.preview import render_thr

    png = render_thr("0 1\n1.57 0.2\n3.14 1\n")
    assert png.startswith(b"\x89PNG")
    assert len(densify([(0.0, 0.0), (0.0, 1.0)])) > 2 
