"""Photo to sand: one continuous path, a twin preview, and the path guardrails."""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from custom_components.homedics_drift.drawing import feedback_text
from custom_components.homedics_drift.patterns import MAX_POINTS, parse_thr, thr_to_wire
from custom_components.homedics_drift.photo_path import (
    _composite,
    build_xy,
    check_rotation,
    configured_camera,
    match_score,
    photo_to_sand,
    resolve_photo_file,
    rotate_xy,
    _open_grey,
)
from custom_components.homedics_drift.patterns import PatternRejected
from custom_components.homedics_drift.twin import render_png


def _png(draw) -> bytes:
    image = Image.new("L", (280, 280), 255)
    draw(ImageDraw.Draw(image))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _circle() -> bytes:
    return _png(lambda draw: draw.ellipse((70, 70, 210, 210), fill=0))


def _star() -> bytes:
    points = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        radius = 100 if index % 2 == 0 else 42
        points.append((140 + radius * math.cos(angle), 140 + radius * math.sin(angle)))
    return _png(lambda draw: draw.polygon(points, fill=0))


def _gaps(points: list[tuple[float, float]]) -> float:
    return max(math.dist(a, b) for a, b in zip(points, points[1:]))


def test_a_bold_shape_becomes_one_path_inside_the_disc() -> None:
    grey = _open_grey(_circle())
    xy, outline, stray = build_xy(
        grey,
        {"spacing": 0.08, "scale": 0.68, "angle": 0.0, "wave": 0.0, "threshold": 0.48, "sweep": 0.05},
    )
    assert len(xy) > 100
    assert len(outline) >= 8
    assert _gaps(xy) < 0.08
    assert max(math.hypot(x, y) for x, y in xy) <= 1.0
    assert max(math.hypot(x, y) for x, y in xy) > 0.9
    assert min(math.hypot(x, y) for x, y in xy) < 0.05
    assert stray < 0.2
    # The outline is a loop, not a dot.
    radii = [math.hypot(x, y) for x, y in outline]
    assert max(radii) - min(radii) < 0.25


def test_rotation_turns_the_picture() -> None:
    assert rotate_xy([(1.0, 0.0)], 90)[0] == pytest.approx((0.0, 1.0), abs=1e-6)
    assert rotate_xy([(0.2, 0.0)], 0) == [(0.2, 0.0)]
    with pytest.raises(PatternRejected, match="between -180 and 180"):
        check_rotation(200)
    with pytest.raises(PatternRejected, match="must be a number"):
        check_rotation("sideways")


def test_fast_twin_picks_a_picture_and_fits_the_table() -> None:
    drawing = photo_to_sand(_star(), detail="fast")
    assert drawing.png.startswith(b"\x89PNG")
    assert drawing.score > 0.5
    assert drawing.recognizable > 0.5
    assert drawing.coverage > 0.4
    assert drawing.stray < 0.25
    polar = parse_thr(drawing.thr)
    assert len(polar) >= 2
    assert len(polar) <= MAX_POINTS
    wire = thr_to_wire(drawing.thr)
    assert len(wire) <= MAX_POINTS
    assert drawing.points == len(polar)


def test_a_long_stray_scores_worse_than_a_clean_fill() -> None:
    assert _composite(1.0, 0.8, 0.0) > _composite(1.0, 0.8, 0.5)
    assert _composite(0.2, 0.8, 0.0) < _composite(0.9, 0.8, 0.05)


def test_twin_png_shows_a_groove() -> None:
    png, sand = render_png([(0.0, 0.0), (0.5, 0.0), (0.5, 0.4)], n=48, size=64, seed=1)
    assert png.startswith(b"\x89PNG")
    assert sand.ballpos is not None
    cut = sand.h < sand.p.depth - 0.006
    assert int(cut.sum()) > 10


def test_the_same_picture_matches_itself() -> None:
    drawing = photo_to_sand(_circle(), rotate=15, detail="fast")
    blank = Image.new("L", (96, 96), 200)
    buffer = BytesIO()
    blank.save(buffer, format="PNG")
    same = match_score(drawing.png, drawing.png)
    other = match_score(drawing.png, buffer.getvalue())
    assert same > 0.9
    assert same > other


def test_photo_paths_stay_in_www_or_media(tmp_path: Path) -> None:
    www = tmp_path / "www"
    media = tmp_path / "media"
    www.mkdir()
    media.mkdir()
    (www / "cat.png").write_bytes(b"png")
    (media / "dog.jpg").write_bytes(b"jpg")
    assert resolve_photo_file(tmp_path, "/local/cat.png") == (www / "cat.png").resolve()
    assert resolve_photo_file(tmp_path, str(media / "dog.jpg")) == (media / "dog.jpg").resolve()
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"no")
    with pytest.raises(PatternRejected, match="/config/www or /config/media"):
        resolve_photo_file(tmp_path, str(outside))
    with pytest.raises(PatternRejected, match="png, jpg"):
        resolve_photo_file(tmp_path, str(www / "notes.txt"))
    (www / "notes.txt").write_text("no", encoding="utf-8")
    with pytest.raises(PatternRejected, match="file in /config/www"):
        resolve_photo_file(tmp_path, "https://example.com/cat.png")


def test_camera_feedback_is_off_until_a_camera_is_saved() -> None:
    assert configured_camera(None) is None
    assert configured_camera({}) is None
    assert configured_camera({"photo_feedback_camera": "  "}) is None
    assert configured_camera({"photo_feedback_camera": "camera.table"}) == "camera.table"
    assert feedback_text("preview", name="Cat") == (
        "Preview ready: Cat. Nothing was sent to the table."
    )
    assert feedback_text("previewing", prompt="a cat") == 'Preparing a sand preview of "a cat"…'
