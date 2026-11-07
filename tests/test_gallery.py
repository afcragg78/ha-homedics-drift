"""Gallery designs stay continuous and inside the upload limit."""

from __future__ import annotations

from custom_components.homedics_drift.gallery import (
    GALLERY,
    gallery_names,
    gallery_polar,
    gallery_thr,
    random_gallery,
)
from custom_components.homedics_drift.patterns import MAX_POINTS, thr_to_wire


def test_gallery_has_many_distinct_named_designs() -> None:
    names = gallery_names()
    assert 30 <= len(names) <= 40
    assert len(names) == len(set(names))
    assert "Lotus Mandala" in names
    assert "Nebula Spiral" in names
    assert len(GALLERY) == len(names)


def test_every_gallery_design_is_a_valid_uploadable_path() -> None:
    for name in gallery_names():
        polar = gallery_polar(name)
        assert polar[0][1] == 0
        assert polar[-1][1] == 1
        assert 400 <= len(polar) <= MAX_POINTS
        text = gallery_thr(name)
        wire = thr_to_wire(text)
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
    assert wire[0][1] == 0
    assert wire[-1][1] == 50000
