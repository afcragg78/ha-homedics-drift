"""Deterministic sand-table designs. No files and no network.

Each design is one continuous polar path. Sampling is kept dense enough to
read as a pattern in sand and short enough to upload.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .patterns import MAX_POINTS, PatternRejected, densify

_GALLERY_LIMIT = 16_000


@dataclass(frozen=True, slots=True)
class GalleryDesign:
    """A named curve the gallery select can show."""

    name: str
    kind: str


def _xy_to_polar(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    scale = max((math.hypot(x, y) for x, y in points), default=1.0) or 1.0
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        radius = min(0.92, math.hypot(x, y) / scale * 0.9)
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, radius))
    return _bookend(polar)


def _bookend(polar: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(polar) < 2:
        raise PatternRejected("that gallery design is empty")
    start = polar[0][0]
    end = polar[-1][0]
    path = [(start, 0.0), *polar, (end, 1.0)]
    step = 0.02
    fitted = densify(path, max_step=step)
    while len(fitted) > _GALLERY_LIMIT and step < 0.06:
        step *= 1.2
        fitted = densify(path, max_step=step)
    if len(fitted) > MAX_POINTS:
        stride = math.ceil(len(fitted) / (MAX_POINTS - 2))
        fitted = fitted[::stride]
    if len(fitted) < 2:
        raise PatternRejected("that gallery design is empty")
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return fitted


def _sample(steps: int, function) -> list[tuple[float, float]]:
    return [function(index / steps) for index in range(steps + 1)]


def _hypotrochoid(outer: float, inner: float, pen: float, turns: float, precess: float = 0.0) -> list[tuple[float, float]]:
    steps = int(turns * 240)

    def point(fraction: float) -> tuple[float, float]:
        theta = turns * 2 * math.pi * fraction
        ratio = (outer - inner) / inner
        return (
            (outer - inner) * math.cos(theta) + pen * math.cos(ratio * theta + precess * theta),
            (outer - inner) * math.sin(theta) - pen * math.sin(ratio * theta + precess * theta),
        )

    return _xy_to_polar(_sample(steps, point))


def _epitrochoid(outer: float, inner: float, pen: float, turns: float, precess: float = 0.0) -> list[tuple[float, float]]:
    steps = int(turns * 240)

    def point(fraction: float) -> tuple[float, float]:
        theta = turns * 2 * math.pi * fraction
        ratio = (outer + inner) / inner
        return (
            (outer + inner) * math.cos(theta) - pen * math.cos(ratio * theta + precess * theta),
            (outer + inner) * math.sin(theta) - pen * math.sin(ratio * theta + precess * theta),
        )

    return _xy_to_polar(_sample(steps, point))


def _rose(k: float, turns: float, scale: float = 0.9) -> list[tuple[float, float]]:
    steps = int(max(turns, 1) * 280)

    def point(fraction: float) -> tuple[float, float]:
        theta = turns * 2 * math.pi * fraction
        return theta, scale * abs(math.cos(k * theta))

    return _bookend(_sample(steps, point))


def _mandala(layers: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    cursor = 0.0
    for k, scale, turns in layers:
        steps = int(turns * 220)
        for index in range(steps + 1):
            local = turns * 2 * math.pi * index / steps
            polar.append((cursor + local, scale * abs(math.cos(k * local))))
        cursor += turns * 2 * math.pi
    return _bookend(polar)


def _lissajous(a: float, b: float, delta: float, turns: float) -> list[tuple[float, float]]:
    steps = int(turns * 260)

    def point(fraction: float) -> tuple[float, float]:
        theta = turns * 2 * math.pi * fraction
        return math.sin(a * theta + delta), math.sin(b * theta)

    return _xy_to_polar(_sample(steps, point))


def _harmonograph(f1: float, f2: float, f3: float, f4: float, decay: float, turns: float) -> list[tuple[float, float]]:
    steps = int(turns * 260)

    def point(fraction: float) -> tuple[float, float]:
        theta = turns * 2 * math.pi * fraction
        fade = math.exp(-decay * fraction)
        return (
            fade * math.sin(f1 * theta) + 0.45 * fade * math.sin(f2 * theta),
            fade * math.sin(f3 * theta + 0.6) + 0.45 * fade * math.sin(f4 * theta),
        )

    return _xy_to_polar(_sample(steps, point))


def _galaxy(arms: int, turns: float) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    steps = int(turns * 180)
    for arm in range(arms):
        shift = arm * 2 * math.pi / arms
        for index in range(steps + 1):
            fraction = index / steps
            polar.append((shift + turns * 2 * math.pi * fraction, 0.92 * fraction))
        for index in range(steps + 1):
            fraction = 1 - index / steps
            polar.append((shift + 0.35 + turns * 2 * math.pi * fraction, 0.92 * fraction))
    return _bookend(polar)


def _chladni(m: int, n: int, turns: float) -> list[tuple[float, float]]:
    steps = int(turns * 320)

    def point(fraction: float) -> tuple[float, float]:
        theta = turns * 2 * math.pi * fraction
        rho = 0.12 + 0.78 * abs(math.sin(m * theta) * math.sin(n * theta))
        return theta, min(0.95, rho)

    return _bookend(_sample(steps, point))


def _wave_rings(rings: int, wobble: int) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    for ring in range(1, rings + 1):
        radius = 0.12 + 0.78 * ring / rings
        steps = 180
        for index in range(steps + 1):
            theta = ring * 2 * math.pi + 2 * math.pi * index / steps
            polar.append((theta, radius + 0.035 * math.sin(wobble * theta)))
    return _bookend(polar)


def _fern(curls: int) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    for curl in range(curls):
        steps = 160
        scale = 0.25 + 0.65 * curl / max(1, curls - 1)
        shift = curl * 2.399
        for index in range(steps + 1):
            fraction = index / steps
            theta = shift + fraction * 3.2 * math.pi
            rho = scale * fraction * (0.55 + 0.45 * math.sin(2 * theta))
            polar.append((theta, min(0.92, rho)))
        for index in range(steps + 1):
            fraction = 1 - index / steps
            theta = shift + 0.4 + fraction * 3.2 * math.pi
            rho = scale * fraction * 0.72
            polar.append((theta, min(0.92, rho)))
    return _bookend(polar)


def _sweeping_arcs(arcs: int, span: float) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    theta = 0.0
    direction = 1.0
    steps = arcs * 80
    for index in range(steps + 1):
        fraction = index / steps
        theta += direction * span / 80
        if index and index % 80 == 0:
            direction *= -1
        polar.append((theta, 0.08 + 0.84 * fraction))
    return _bookend(polar)


def _petals(lobes: int, layers: int) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    cursor = 0.0
    for layer in range(layers):
        scale = 0.45 + 0.45 * layer / max(1, layers - 1)
        turns = 1.0
        steps = 240
        for index in range(steps + 1):
            local = turns * 2 * math.pi * index / steps
            rho = scale * abs(math.sin(lobes * local / 2))
            polar.append((cursor + local + layer * 0.2, rho))
        cursor += turns * 2 * math.pi
    return _bookend(polar)


def _build(kind: str, rng: random.Random | None = None) -> list[tuple[float, float]]:
    jitter = 0.0 if rng is None else rng.uniform(-0.08, 0.08)
    turns = 6.0 if rng is None else rng.uniform(5.0, 8.0)
    if kind == "lotus":
        return _mandala([(2.5, 0.55, 2), (5, 0.78, 2), (8, 0.92, 2)])
    if kind == "temple":
        return _rose(7 / 2 + jitter, 4)
    if kind == "moonflower":
        return _rose(5 / 2, 5)
    if kind == "iris":
        return _rose(8 / 3, 4)
    if kind == "dahlia":
        return _rose(11 / 3, 3.5)
    if kind == "nebula":
        return _galaxy(3, 5 + jitter)
    if kind == "twin":
        return _galaxy(2, 6)
    if kind == "ember":
        return _galaxy(4, 4)
    if kind == "orbit":
        return _hypotrochoid(11, 4, 6, turns, 0.15)
    if kind == "epicycle":
        return _epitrochoid(7, 3, 4, turns, 0.05)
    if kind == "precess":
        return _hypotrochoid(13, 5, 7, 7, 0.35)
    if kind == "coins":
        return _hypotrochoid(9, 2, 5, 8, 0.0)
    if kind == "velvet":
        return _hypotrochoid(8, 3, 2.5, 9, 0.22)
    if kind == "amber":
        return _epitrochoid(5, 2, 3.5, 7, 0.18)
    if kind == "pearl":
        return _hypotrochoid(12, 5, 3, 6, 0.08)
    if kind == "lissajous":
        return _lissajous(3, 2, 0.4, 3)
    if kind == "figure":
        return _lissajous(3, 4, math.pi / 2, 2.5)
    if kind == "lace":
        return _harmonograph(3, 5, 4, 7, 0.35, 4)
    if kind == "silk":
        return _harmonograph(2, 3.1, 5, 4.2, 0.55, 5)
    if kind == "pendulum":
        return _harmonograph(5, 8, 3, 6, 0.8, 4)
    if kind == "petals":
        return _petals(6, 3)
    if kind == "sixfold":
        return _petals(8, 2)
    if kind == "chladni":
        return _chladni(4, 3, 5)
    if kind == "nodal":
        return _chladni(5, 2, 6)
    if kind == "rings":
        return _wave_rings(7, 6)
    if kind == "ripple":
        return _wave_rings(5, 9)
    if kind == "tide":
        return _wave_rings(8, 4)
    if kind == "fern":
        return _fern(5)
    if kind == "fiddle":
        return _fern(4)
    if kind == "whorl":
        return _fern(6)
    if kind == "sweep":
        return _sweeping_arcs(9, 2.4)
    if kind == "cathedral":
        return _sweeping_arcs(7, 3.1)
    if kind == "veil":
        return _sweeping_arcs(11, 1.8)
    if kind == "coral":
        return _mandala([(3.5, 0.5, 2), (7 / 2, 0.72, 2), (6, 0.9, 1.5)])
    if kind == "starflower":
        return _mandala([(5, 0.62, 2), (5 / 2, 0.88, 2)])
    if kind == "aurora":
        return _rose(9 / 4, 6, 0.86)
    if kind == "lattice":
        return _rose(13 / 5, 5, 0.88)
    if kind == "comet":
        return _galaxy(1, 8)
    raise PatternRejected("that gallery design is not in the list")


GALLERY: tuple[GalleryDesign, ...] = (
    GalleryDesign("Lotus Mandala", "lotus"),
    GalleryDesign("Temple Rose", "temple"),
    GalleryDesign("Moonflower", "moonflower"),
    GalleryDesign("Iris Wheel", "iris"),
    GalleryDesign("Dahlia Crown", "dahlia"),
    GalleryDesign("Nebula Spiral", "nebula"),
    GalleryDesign("Twin Galaxies", "twin"),
    GalleryDesign("Ember Arms", "ember"),
    GalleryDesign("Orbit Weave", "orbit"),
    GalleryDesign("Epicyclic Crown", "epicycle"),
    GalleryDesign("Slow Precession", "precess"),
    GalleryDesign("Nested Coins", "coins"),
    GalleryDesign("Velvet Gear", "velvet"),
    GalleryDesign("Amber Orbit", "amber"),
    GalleryDesign("Pearl Cycloid", "pearl"),
    GalleryDesign("Lissajous Bowl", "lissajous"),
    GalleryDesign("Drifted Figure", "figure"),
    GalleryDesign("Harmonic Lace", "lace"),
    GalleryDesign("Pendulum Silk", "silk"),
    GalleryDesign("Fading Swirl", "pendulum"),
    GalleryDesign("Interlocking Petals", "petals"),
    GalleryDesign("Sixfold Bloom", "sixfold"),
    GalleryDesign("Chladni Cross", "chladni"),
    GalleryDesign("Nodal Rings", "nodal"),
    GalleryDesign("Wave Rings", "rings"),
    GalleryDesign("Ripple Well", "ripple"),
    GalleryDesign("Tide Circles", "tide"),
    GalleryDesign("Fern Curl", "fern"),
    GalleryDesign("Fiddlehead", "fiddle"),
    GalleryDesign("Golden Whorl", "whorl"),
    GalleryDesign("Sweeping Arc", "sweep"),
    GalleryDesign("Cathedral Sweep", "cathedral"),
    GalleryDesign("Sisyphus Veil", "veil"),
    GalleryDesign("Coral Mandala", "coral"),
    GalleryDesign("Starflower", "starflower"),
    GalleryDesign("Aurora Spiral", "aurora"),
    GalleryDesign("Lattice Rose", "lattice"),
    GalleryDesign("Comet Tail", "comet"),
)


_PICTURES: dict[str, str] = {}


def gallery_picture(name: str) -> str | None:
    """Small data URL for the select row of the design that is chosen."""
    if name not in gallery_names():
        return None
    cached = _PICTURES.get(name)
    if cached is None:
        import base64

        from .preview import render_preview

        png = render_preview(gallery_polar(name), size=96)
        cached = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        _PICTURES[name] = cached
    return cached


def gallery_names() -> list[str]:
    """Pleasant names, in display order."""
    return [design.name for design in GALLERY]


def _kind(name: str) -> str:
    for design in GALLERY:
        if design.name == name:
            return design.kind
    raise PatternRejected(f"unknown gallery design {name}")


def gallery_polar(name: str) -> list[tuple[float, float]]:
    """The canonical path for one named design."""
    return _build(_kind(name))


def gallery_thr(name: str) -> str:
    """Theta-rho text for one named design."""
    polar = gallery_polar(name)
    lines = [f"{theta:.6f} {min(1.0, max(0.0, rho)):.6f}" for theta, rho in polar]
    return "\n".join(lines) + "\n"


def random_gallery(seed: int) -> tuple[str, str]:
    """A seeded variation of one gallery design. The same seed repeats."""
    rng = random.Random(seed)
    design = GALLERY[rng.randrange(len(GALLERY))]
    polar = _build(design.kind, rng)
    title = f"{design.name} {seed % 10000}"
    lines = [f"{theta:.6f} {min(1.0, max(0.0, rho)):.6f}" for theta, rho in polar]
    return title, "\n".join(lines) + "\n"
