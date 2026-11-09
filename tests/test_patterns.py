"""Pattern upload planning. No table and no Home Assistant."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from custom_components.homedics_drift.patterns import (
    STORAGE_CAP,
    USER_ID_MIN,
    CleanList,
    PatternLibrary,
    PatternRejected,
    allocate_id,
    choose_clean_upload_id,
    clean_play_order,
    cleaning_spiral,
    deletion_refusal,
    find_stock_clean,
    densify,
    documents_from_download,
    gcode_to_thr,
    IMPORT_EMPTY,
    github_folder_api,
    github_raw_url,
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


def test_stock_clean_is_preferred_and_the_spiral_is_protected() -> None:
    stored = {3, 9, 40}
    lists = [
        CleanList(1, "clean", (3, 9)),
        CleanList(2, "Evening", (40,)),
    ]
    assert find_stock_clean(lists, {}, stored) == 3
    assert find_stock_clean([], {3: "Clean"}, stored) == 3
    assert find_stock_clean([], {50000: "Clean"}, stored | {50000}) is None
    assert find_stock_clean([CleanList(4, "Other", (3,))], {}, stored) is None
    spiral = cleaning_spiral()
    assert spiral[0][1] == 0
    assert spiral[-1] == (spiral[-1][0], 1.0)
    assert spiral[-1][0] == pytest.approx(20 * 2 * math.pi)
    assert len(spiral) < 8000
    assert choose_clean_upload_id(set(), None, None) == 50000
    assert choose_clean_upload_id({50000}, None, None) != 50000
    assert choose_clean_upload_id({50000}, 12, 50010) == 50010
    library = PatternLibrary()
    library.remember(50000, "Clean", "0 0\n", protected=True)
    assert deletion_refusal(
        50000,
        stored={50000},
        playing=None,
        uploaded={50000},
        protected=library.protected_ids(),
    ) == "the clean pattern is kept"
    assert clean_play_order(40, 3, clean_before=True) == [3, 40]
    assert clean_play_order(3, 3, clean_before=True) == [3]
    assert clean_play_order(40, 3, clean_before=False) == [40]
    restored = PatternLibrary.from_dict(library.to_dict())
    assert restored.protected_clean_id() == 50000
    restored.clean_before = True
    assert PatternLibrary.from_dict(restored.to_dict()).clean_before is True


def test_favorites_and_https_imports_are_local_rules() -> None:
    from custom_components.homedics_drift.patterns import (
        documents_from_download,
        https_pattern_url,
    )

    library = PatternLibrary()
    library.set_favorite("Lotus Mandala", True)
    library.set_favorite("Lotus Mandala", False)
    library.set_favorite("Nebula Spiral", True)
    assert library.favorite_names() == ["Nebula Spiral"]
    assert PatternLibrary.from_dict(library.to_dict()).favorite_names() == ["Nebula Spiral"]
    assert https_pattern_url("https://example.com/a.thr").endswith("a.thr")
    with pytest.raises(PatternRejected):
        https_pattern_url("http://example.com/a.thr")
    with pytest.raises(PatternRejected):
        https_pattern_url("https://localhost/a.thr")
    body = b"0 0\n1 0.5\n"
    assert documents_from_download("https://example.com/lotus.thr", body)[0][0] == "lotus"
    import io
    import zipfile

    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr("pack/rose.thr", "0 0\n0.2 1\n")
        archive.writestr("notes.txt", "hello")
    docs = documents_from_download("pack.zip", packed.getvalue())
    assert docs[0][0] == "rose"
    assert parse_thr(docs[0][1])[0][1] == 0


def test_github_blob_and_gcode_become_a_thr_path() -> None:
    raw = github_raw_url(
        "https://github.com/fly115/Sandtable-patterns/blob/master/example.thr"
    )
    assert raw == "https://raw.githubusercontent.com/fly115/Sandtable-patterns/master/example.thr"
    folder = github_folder_api("https://github.com/example/patterns/tree/main/gcode")
    assert folder == "https://api.github.com/repos/example/patterns/contents/gcode?ref=main"
    assert "gcode" in IMPORT_EMPTY
    assert ".thr" in IMPORT_EMPTY
    assert github_raw_url("https://raw.githubusercontent.com/example/a.thr").endswith("a.thr")
    text = gcode_to_thr("G21\nG90\nG1 X0 Y0\nG1 X10 Y0\nG1 X10 Y10\nG1 X0 Y10\n")
    polar = parse_thr(text)
    assert len(polar) >= 4
    assert max(rho for _theta, rho in polar) <= 1
    loaded = documents_from_download("square.gcode", text.encode() if False else b"G1 X0 Y0\nG1 X8 Y0\nG1 X8 Y8\n")
    assert loaded[0][0] == "square"
    assert len(parse_thr(loaded[0][1])) >= 2


def test_user_patterns_skip_the_protected_clean_spiral() -> None:
    library = PatternLibrary()
    library.remember(50001, "Star", "0 0\n1 1\n", source="ai")
    library.remember(50000, "Clean", "0 0\n1 1\n", protected=True)
    assert [record.name for record in library.user_patterns()] == ["Star"]


def test_preview_is_a_png() -> None:
    pytest.importorskip("PIL")
    from custom_components.homedics_drift.preview import render_thr

    png = render_thr("0 1\n1.57 0.2\n3.14 1\n")
    assert png.startswith(b"\x89PNG")
    assert len(densify([(0.0, 0.0), (0.0, 1.0)])) > 2 
