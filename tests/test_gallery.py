"""Gallery designs stay continuous and inside the upload limit."""

from __future__ import annotations

import math

from custom_components.homedics_drift.gallery import (
    CATEGORY_ORDER,
    GALLERY,
    gallery_categories,
    gallery_names,
    gallery_polar,
    gallery_thr,
    random_gallery,
    trace_points,
)
from custom_components.homedics_drift.patterns import MAX_POINTS, thr_to_wire


def _longest_step(polar: list[tuple[float, float]]) -> float:
    longest = 0.0
    for (theta, rho), (nxt_theta, nxt_rho) in zip(polar, polar[1:], strict=False):
        x0, y0 = rho * math.cos(theta), rho * math.sin(theta)
        x1, y1 = nxt_rho * math.cos(nxt_theta), nxt_rho * math.sin(nxt_theta)
        longest = max(longest, math.hypot(x1 - x0, y1 - y0))
    return longest


def test_gallery_has_many_distinct_named_designs() -> None:
    names = gallery_names()
    assert len(names) == 40
    assert len(names) == len(set(names))
    assert "Lotus Mandala" in names
    assert "Drift Away" in names
    assert "Nebula Spiral" in names
    assert len(GALLERY) == len(names)
    categories = gallery_categories()
    assert set(categories.values()) == set(CATEGORY_ORDER)
    assert list(dict.fromkeys(categories[name] for name in names)) == list(CATEGORY_ORDER)


def test_every_gallery_design_is_a_valid_uploadable_path() -> None:
    for name in gallery_names():
        polar = gallery_polar(name)
        assert polar[0][1] == 0
        assert polar[-1][1] == 1
        assert 800 <= len(polar) <= MAX_POINTS
        assert _longest_step(polar) < 0.08
        text = gallery_thr(name)
        wire = thr_to_wire(text)
        assert 1_500 <= len(wire) <= MAX_POINTS
        assert wire[0][1] == 0
        assert wire[-1][1] == 50000
        assert gallery_thr(name) == text


def test_random_gallery_is_seeded_and_not_the_canonical_name() -> None:
    first_name, first = random_gallery(1842)
    again_name, again = random_gallery(1842)
    other_name, other = random_gallery(99)
    assert first_name == again_name
    assert first == again
    assert first != other or first_name != other_name
    assert first_name not in gallery_names()
    wire = thr_to_wire(first)
    assert len(wire) >= 1_500
    assert wire[0][1] == 0
    assert wire[-1][1] == 50000


def test_trace_points_follow_progress_without_the_full_upload() -> None:
    polar = gallery_polar("Lotus Mandala")
    traced = trace_points(polar, limit=400)
    assert 2 <= len(traced) <= 400
    assert traced[0][1] == 0
    assert traced[-1][1] == 1
