"""Oasis engravings stay one continuous path inside the upload limit."""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw

from custom_components.homedics_drift.oasis import (
    STYLE_CONTOURS,
    STYLE_LINE,
    STYLE_SPIRAL,
    art_from_image,
    art_from_points,
    contour_xy,
    normalize_art_style,
    spiral_xy,
)
from custom_components.homedics_drift.patterns import MAX_POINTS, parse_thr, thr_to_wire
from custom_components.homedics_drift.preview import render_preview


def _blob(size: int = 72) -> list[list[float]]:
    grid = []
    for y in range(size):
        row = []
        for x in range(size):
            nx = (x / (size - 1)) * 2 - 1
            ny = 1 - (y / (size - 1)) * 2
            distance = math.hypot(nx * 1.3, ny)
            row.append(max(0.0, 1 - distance) if math.hypot(nx, ny) <= 1 else 0.0)
        grid.append(row)
    return grid


def _longest(text: str) -> float:
    polar = parse_thr(text)
    longest = 0.0
    for (theta, rho), (nxt_theta, nxt_rho) in zip(polar, polar[1:], strict=False):
        x0, y0 = rho * math.cos(theta), rho * math.sin(theta)
        x1, y1 = nxt_rho * math.cos(nxt_theta), nxt_rho * math.sin(nxt_theta)
        longest = max(longest, math.hypot(x1 - x0, y1 - y0))
    return longest


def _assert_upload(text: str) -> None:
    polar = parse_thr(text)
    assert polar[0][1] == 0
    assert polar[-1][1] == 1
    assert _longest(text) < 0.08
    wire = thr_to_wire(text)
    assert 400 <= len(wire) <= MAX_POINTS
    assert wire[0][1] == 0
    assert wire[-1][1] == 50000
    render_preview(polar, size=64)


def _png() -> bytes:
    image = Image.new("L", (96, 96), 240)
    draw = ImageDraw.Draw(image)
    draw.ellipse((24, 18, 72, 78), fill=20)
    draw.polygon([(48, 16), (70, 70), (26, 70)], fill=0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_contour_and_spiral_styles_upload() -> None:
    grid = _blob()
    contours = contour_xy(grid, levels=16)
    assert len(contours) > 200
    spiral = spiral_xy(grid, turns=24)
    assert len(spiral) > 200
    for style in (STYLE_CONTOURS, STYLE_SPIRAL, STYLE_LINE):
        _assert_upload(art_from_image(_png(), style))


def test_text_fallback_echoes_the_line_and_fills_the_disc() -> None:
    star = []
    for index in range(40):
        theta = 2 * math.pi * index / 40
        rho = 0.7 if index % 2 == 0 else 0.25
        star.append((rho * math.cos(theta), rho * math.sin(theta)))
    plain = art_from_points(star, STYLE_LINE)
    filled = art_from_points(star, STYLE_CONTOURS)
    _assert_upload(plain)
    _assert_upload(filled)
    assert len(parse_thr(filled)) >= len(parse_thr(plain))
    assert normalize_art_style("nope") == STYLE_CONTOURS
    assert normalize_art_style("spiral") == STYLE_SPIRAL
