"""Picture to sand stays one path, and contours fill more of the disc than a line."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from custom_components.homedics_drift.patterns import parse_thr
from custom_components.homedics_drift.picture import (
    STYLE_CONTOURS,
    STYLE_LINE,
    art_from_image,
    study_polar,
)


def _blob() -> bytes:
    image = Image.new("L", (80, 80), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((22, 18, 58, 62), fill=0)
    draw.ellipse((30, 30, 38, 40), fill=255)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _span(text: str) -> tuple[float, float, int]:
    polar = parse_thr(text)
    rhos = [rho for _theta, rho in polar]
    return min(rhos), max(rhos), len(polar)


def test_a_photo_becomes_one_contour_path() -> None:
    thr = art_from_image(_blob(), STYLE_CONTOURS)
    _low, high, count = _span(thr)
    assert high == 1
    assert count >= 800
    outer = sum(1 for _theta, rho in parse_thr(thr) if rho > 0.7)
    assert outer > 40


def test_line_drawing_is_shorter_than_contours() -> None:
    data = _blob()
    line = art_from_image(data, STYLE_LINE)
    field = art_from_image(data, "Contours")
    assert _span(line)[2] < _span(field)[2]


def test_showcase_studies_reach_the_rim() -> None:
    for name in ("tiger", "koi", "lotus"):
        polar = study_polar(name)
        assert polar[0][1] == 0
        assert polar[-1][1] == 1
        assert len(polar) >= 800
