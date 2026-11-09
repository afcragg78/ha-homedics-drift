"""Dense sand-table designs. No files and no network.

Each design is one continuous polar path. Copies of a petal or a ring are
joined along the centre or the rim, so the ball does not cut straight across
the table between them. Sampling stays inside the upload limit.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .mazes import maze_polar
from .patterns import MAX_POINTS, PatternRejected, densify
from .sisyphus_tracks import CATALOG, track_polar

CATEGORY_ORDER: tuple[str, ...] = (
    "Mandalas",
    "Florals",
    "Geometric",
    "Spirals",
    "Waves",
    "Cosmic",
    "Mazes & Fills",
    "Sisyphus Classics",
)
_TARGET = 9_000


@dataclass(frozen=True, slots=True)
class GalleryDesign:
    """A named curve the gallery select can show."""

    name: str
    kind: str
    category: str


def _clamp(theta: float, rho: float) -> tuple[float, float]:
    return theta, min(0.97, max(0.0, rho))


def _join_center(path: list[tuple[float, float]], nxt: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Meet the next stroke at the centre, where a theta change does not travel."""
    if not nxt:
        return path
    if not path:
        return list(nxt)
    out = list(path)
    out.append((out[-1][0], 0.02))
    out.append((nxt[0][0], 0.02))
    out.extend(nxt)
    return out


def _join_rim(path: list[tuple[float, float]], nxt: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Walk the rim, the short way, instead of a chord."""
    if not nxt:
        return path
    if not path:
        return list(nxt)
    out = list(path)
    start = out[-1][0]
    end = nxt[0][0]
    delta = (end - start + math.pi) % (2 * math.pi) - math.pi
    steps = max(2, int(abs(delta) / 0.06))
    for index in range(1, steps + 1):
        out.append((start + delta * index / steps, 0.96))
    out.extend(nxt)
    return out


def _petals(copies: int, peak: float, pinch: float, phase: float, width: float) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    half = math.pi / max(1, copies) * width
    steps = max(20, int(28 + copies))
    for copy in range(copies):
        center = phase + 2 * math.pi * copy / copies
        for index in range(steps + 1):
            unit = index / steps
            angle = center + (unit - 0.5) * 2 * half
            rho = peak * math.sin(math.pi * unit) ** pinch
            path.append(_clamp(angle, rho))
    return path


def _rose(k: float, scale: float, turns: float, phase: float) -> list[tuple[float, float]]:
    steps = int(max(turns, 1.0) * 240)
    path: list[tuple[float, float]] = []
    for index in range(steps + 1):
        theta = phase + turns * 2 * math.pi * index / steps
        path.append(_clamp(theta, scale * abs(math.cos(k * (theta - phase)))))
    return path


def _ring(lobes: int, radius: float, amp: float, phase: float, turns: float = 1.0) -> list[tuple[float, float]]:
    steps = int(max(8, lobes) * 18 * turns)
    path: list[tuple[float, float]] = []
    for index in range(steps + 1):
        theta = phase + turns * 2 * math.pi * index / steps
        path.append(_clamp(theta, radius + amp * math.sin(lobes * (theta - phase))))
    return path


def _burst(rays: int, inner: float, outer: float, phase: float, hook: float = 0.07) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    steps = 14
    for ray in range(rays):
        angle = phase + 2 * math.pi * ray / rays
        stroke: list[tuple[float, float]] = []
        for index in range(steps + 1):
            rho = inner + (outer - inner) * index / steps
            stroke.append(_clamp(angle, rho))
        for index in range(steps + 1):
            rho = outer - (outer - inner) * index / steps
            stroke.append(_clamp(angle + hook, rho))
        nxt = phase + 2 * math.pi * (ray + 1) / rays
        delta = (nxt - (angle + hook) + math.pi) % (2 * math.pi) - math.pi
        arc_steps = max(2, int(abs(delta) / 0.08))
        for index in range(1, arc_steps + 1):
            stroke.append(_clamp(angle + hook + delta * index / arc_steps, inner))
        path.extend(stroke)
    return path


def _star(points: int, skip: int, radius: float, phase: float) -> list[tuple[float, float]]:
    vertices: list[tuple[float, float]] = []
    for index in range(points):
        angle = phase + 2 * math.pi * index / points - math.pi / 2
        vertices.append((radius * math.cos(angle), radius * math.sin(angle)))
    path: list[tuple[float, float]] = []
    cursor = 0
    previous: float | None = None
    for _ in range(points):
        x0, y0 = vertices[cursor]
        cursor = (cursor + skip) % points
        x1, y1 = vertices[cursor]
        samples = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.018))
        for index in range(samples + 1):
            unit = index / samples
            x = x0 + (x1 - x0) * unit
            y = y0 + (y1 - y0) * unit
            rho = min(0.97, math.hypot(x, y))
            theta = math.atan2(y, x)
            if previous is not None:
                while theta - previous > math.pi:
                    theta -= 2 * math.pi
                while theta - previous < -math.pi:
                    theta += 2 * math.pi
            previous = theta
            path.append((theta, rho))
    return path


def _spiral(arms: int, turns: float, phase: float, wobble: float) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    steps = int(turns * 100)
    for arm in range(arms):
        shift = phase + arm * 2 * math.pi / max(1, arms)
        stroke: list[tuple[float, float]] = []
        for index in range(steps + 1):
            fraction = index / steps
            theta = shift + turns * 2 * math.pi * fraction
            rho = 0.05 + 0.9 * fraction + wobble * math.sin(3 * theta) * fraction
            stroke.append(_clamp(theta, rho))
        for index in range(steps + 1):
            fraction = 1 - index / steps
            theta = shift + 0.18 + turns * 2 * math.pi * fraction
            rho = 0.05 + 0.84 * fraction
            stroke.append(_clamp(theta, rho))
        path = _join_center(path, stroke)
    return path


def _xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    scale = max((math.hypot(x, y) for x, y in points), default=1.0) or 1.0
    path: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        rho = min(0.96, math.hypot(x, y) / scale * 0.92)
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        path.append((theta, rho))
    return path


def _hypo(outer: float, inner: float, pen: float, turns: float, phase: float) -> list[tuple[float, float]]:
    steps = int(turns * 220)
    points: list[tuple[float, float]] = []
    ratio = (outer - inner) / inner
    for index in range(steps + 1):
        theta = phase + turns * 2 * math.pi * index / steps
        points.append(
            (
                (outer - inner) * math.cos(theta) + pen * math.cos(ratio * theta),
                (outer - inner) * math.sin(theta) - pen * math.sin(ratio * theta),
            )
        )
    return _xy(points)


def _epi(outer: float, inner: float, pen: float, turns: float, phase: float) -> list[tuple[float, float]]:
    steps = int(turns * 220)
    points: list[tuple[float, float]] = []
    ratio = (outer + inner) / inner
    for index in range(steps + 1):
        theta = phase + turns * 2 * math.pi * index / steps
        points.append(
            (
                (outer + inner) * math.cos(theta) - pen * math.cos(ratio * theta),
                (outer + inner) * math.sin(theta) - pen * math.sin(ratio * theta),
            )
        )
    return _xy(points)


def _lissajous(a: float, b: float, delta: float, turns: float, phase: float) -> list[tuple[float, float]]:
    steps = int(turns * 280)
    points: list[tuple[float, float]] = []
    for index in range(steps + 1):
        theta = phase + turns * 2 * math.pi * index / steps
        points.append((math.sin(a * theta + delta), math.sin(b * theta)))
    return _xy(points)


def _unwrap(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    previous: float | None = None
    for theta, rho in path:
        if previous is not None:
            while theta - previous > math.pi:
                theta -= 2 * math.pi
            while theta - previous < -math.pi:
                theta += 2 * math.pi
        previous = theta
        out.append((theta, min(0.98, max(0.0, rho))))
    return out


def _decimate(path: list[tuple[float, float]], min_step: float, limit: int) -> list[tuple[float, float]]:
    if not path:
        return []
    kept = [path[0]]
    for theta, rho in path[1:]:
        prev_theta, prev_rho = kept[-1]
        distance = math.hypot(rho - prev_rho, (theta - prev_theta) * max(rho, prev_rho, 0.02))
        if distance >= min_step:
            kept.append((theta, rho))
    if len(kept) > limit:
        stride = math.ceil(len(kept) / limit)
        kept = kept[::stride]
    if kept[-1] != path[-1]:
        kept.append(path[-1])
    return kept


def _radial(theta: float, start: float, end: float, step: float) -> list[tuple[float, float]]:
    span = abs(end - start)
    count = max(1, math.ceil(span / step))
    return [(theta, start + (end - start) * index / count) for index in range(count + 1)]


def _fit(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(path) < 2:
        raise PatternRejected("that gallery design is empty")
    path = _unwrap(path)
    step = 0.016
    fitted = densify(_decimate(path, step * 0.75, _TARGET), max_step=step)
    while len(fitted) > _TARGET and step < 0.04:
        step *= 1.2
        fitted = densify(_decimate(path, step * 0.8, _TARGET), max_step=step)
    if len(fitted) < 2:
        raise PatternRejected("that gallery design is empty")
    head = _radial(fitted[0][0], 0.0, fitted[0][1], step)
    tail = _radial(fitted[-1][0], fitted[-1][1], 1.0, step)
    fitted = head + fitted[1:-1] + tail
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    if len(densify(fitted, max_step=0.01)) > 20_000:
        stride = math.ceil(len(fitted) / 9_000)
        fitted = densify(fitted[::stride], max_step=0.015)
        fitted[0] = (fitted[0][0], 0.0)
        fitted[-1] = (fitted[-1][0], 1.0)
    return fitted


def _stack(*parts: list[tuple[float, float]], rim: bool = False) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    join = _join_rim if rim else _join_center
    for part in parts:
        if part:
            path = join(path, part)
    return path


def _build(kind: str, rng: random.Random | None = None) -> list[tuple[float, float]]:
    if kind.startswith("sisyphus:"):
        return track_polar(kind.split(":", 1)[1])
    if kind.startswith("maze:"):
        return maze_polar(kind.split(":", 1)[1])
    phase = 0.0 if rng is None else rng.uniform(0.0, 0.45)
    pinch = 1.15 if rng is None else rng.uniform(0.9, 1.35)
    made = _COMPOSE[kind](phase, pinch)
    return _fit(made)


def _compose_table() -> dict[str, object]:
    def lotus(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _petals(12, 0.42, pinch, phase, 0.95),
            _petals(18, 0.66, pinch, phase + 0.08, 0.8),
            _petals(24, 0.9, pinch, phase, 0.7),
            _ring(24, 0.94, 0.025, phase),
        )

    def crown(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _petals(12, 0.38, pinch, phase, 1.05),
            _petals(12, 0.62, pinch, phase + 0.13, 0.85),
            _petals(12, 0.9, pinch, phase, 0.65),
            _burst(24, 0.2, 0.55, phase, 0.05),
        )

    def drift_away(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _star(12, 5, 0.42, phase),
            _star(12, 5, 0.66, phase + 0.08),
            _star(12, 5, 0.9, phase),
            _petals(12, 0.96, pinch, phase, 0.75),
        )

    def palace(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _hypo(12, 5, 7, 6, phase),
            _petals(16, 0.92, pinch, phase, 0.7),
            _ring(16, 0.95, 0.02, phase),
        )

    def sun_court(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _burst(36, 0.12, 0.48, phase, 0.04),
            _burst(24, 0.5, 0.92, phase + 0.04, 0.05),
            _petals(12, 0.96, pinch, phase, 0.9),
        )

    def midnight(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _rose(6, 0.45, 1, phase),
            _rose(9, 0.7, 1, phase),
            _rose(12, 0.94, 1, phase),
            _ring(12, 0.96, 0.02, phase),
        )

    def saffron(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _petals(10, 0.4, pinch, phase, 1.1),
            _petals(20, 0.68, pinch, phase + 0.05, 0.75),
            _petals(30, 0.94, pinch, phase, 0.6),
        )

    def temple(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _rose(3.5, 0.72, 4, phase),
            _petals(14, 0.95, pinch, phase, 0.8),
            _ring(14, 0.93, 0.03, phase),
        )

    def moonflower(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _rose(2.5, 0.55, 4, phase),
            _petals(8, 0.78, pinch, phase, 1.2),
            _petals(16, 0.95, pinch, phase + 0.1, 0.7),
        )

    def dahlia(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _petals(24, 0.48, pinch, phase, 0.55),
            _petals(32, 0.72, pinch, phase + 0.04, 0.45),
            _petals(40, 0.95, pinch, phase, 0.4),
        )

    def peony(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _epi(7, 3, 5, 6, phase),
            _petals(16, 0.9, pinch, phase, 0.85),
            _ring(16, 0.95, 0.028, phase),
        )

    def iris(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _spiral(3, 5, phase, 0.04),
            _petals(9, 0.92, pinch, phase, 1.0),
        )

    def camellia(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _ring(12, 0.28, 0.03, phase),
            _ring(16, 0.48, 0.035, phase),
            _ring(20, 0.68, 0.03, phase),
            _petals(12, 0.95, pinch, phase, 0.9),
            rim=True,
        )

    def wisteria(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _spiral(4, 3.4, phase, 0.05)

    def orchid(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _star(8, 3, 0.7, phase),
            _petals(8, 0.95, pinch, phase, 1.15),
            _ring(8, 0.9, 0.04, phase),
        )

    def magnolia(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _petals(6, 0.55, pinch, phase, 1.35),
            _petals(12, 0.82, pinch, phase + 0.12, 1.0),
            _ring(12, 0.94, 0.03, phase),
        )

    def star_lattice(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _star(12, 5, 0.4, phase),
            _star(12, 5, 0.68, phase),
            _star(12, 5, 0.94, phase + 0.06),
            _ring(12, 0.96, 0.015, phase),
        )

    def hex_tiling(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _star(6, 2, 0.36, phase),
            _star(6, 2, 0.62, phase + 0.15),
            _star(6, 2, 0.9, phase),
            _ring(6, 0.95, 0.02, phase),
        )

    def compass(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _burst(32, 0.08, 0.96, phase, 0.035),
            _petals(4, 0.7, pinch, phase, 0.5),
            _petals(8, 0.95, pinch, phase + 0.2, 0.45),
        )

    def octagon(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _star(8, 3, 0.34, phase),
            _star(8, 3, 0.56, phase),
            _star(8, 3, 0.78, phase),
            _star(8, 3, 0.96, phase + 0.1),
        )

    def diamond(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _star(4, 1, 0.4, phase),
            _star(4, 1, 0.4, phase + math.pi / 4),
            _star(8, 3, 0.72, phase),
            _star(8, 3, 0.94, phase),
            _ring(8, 0.96, 0.02, phase),
        )

    def cathedral(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _star(16, 6, 0.55, phase),
            _star(16, 6, 0.9, phase),
            _petals(16, 0.96, pinch, phase, 0.6),
        )

    def whorl(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _spiral(1, 14, phase, 0.05)

    def nautilus(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(_spiral(1, 9, phase, 0.08), _ring(1, 0.95, 0.0, phase))

    def fern(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _spiral(6, 3.2, phase, 0.07)

    def helix(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _spiral(2, 10, phase, 0.03)

    def spiral_bloom(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _spiral(3, 6, phase, 0.02),
            _petals(12, 0.55, pinch, phase, 0.8),
            _petals(18, 0.92, pinch, phase + 0.07, 0.65),
        )

    def fibonacci(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _spiral(5, 3.0, phase + 2.399, 0.04)

    def tide(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        rings = [_ring(10 + 2 * index, 0.18 + index * 0.1, 0.028, phase + index * 0.05) for index in range(8)]
        return _stack(*rings, rim=True)

    def scallop(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _ring(12, 0.32, 0.04, phase),
            _ring(18, 0.55, 0.045, phase),
            _ring(24, 0.78, 0.04, phase),
            _ring(32, 0.95, 0.03, phase),
            rim=True,
        )

    def ripple(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _ring(8, 0.3, 0.02, phase),
            _ring(14, 0.5, 0.03, phase),
            _ring(20, 0.72, 0.03, phase),
            _ring(28, 0.94, 0.025, phase),
            _burst(18, 0.15, 0.4, phase, 0.06),
            rim=True,
        )

    def lace(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _lissajous(3, 5, 0.6, 4, phase),
            _lissajous(5, 8, 1.1, 3, phase),
            _ring(20, 0.95, 0.02, phase),
        )

    def silk(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _lissajous(2, 3, math.pi / 2, 5, phase),
            _ring(12, 0.55, 0.04, phase),
            _ring(18, 0.82, 0.035, phase),
            rim=True,
        )

    def ring_tide(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        rings = [_ring(16, 0.16 + index * 0.07, 0.02, phase + index * 0.02) for index in range(12)]
        return _stack(*rings, rim=True)

    def nebula(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _spiral(3, 3.2, phase, 0.05),
            _rose(4, 0.9, 2, phase),
            _petals(12, 0.96, pinch, phase, 0.7),
        )

    def twin(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _spiral(2, 9, phase, 0.055)

    def orbit(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _hypo(11, 4, 6.5, 7, phase),
            _hypo(9, 4, 3, 6, phase + 0.2),
            _ring(12, 0.95, 0.02, phase),
        )

    def aurora(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _epi(8, 3, 5, 7, phase),
            _petals(18, 0.94, pinch, phase, 0.75),
            _ring(18, 0.96, 0.02, phase),
        )

    def comet(phase: float, pinch: float) -> list[tuple[float, float]]:
        del pinch
        return _stack(
            _spiral(1, 12, phase, 0.04),
            _burst(28, 0.2, 0.7, phase, 0.04),
            _ring(20, 0.94, 0.025, phase),
        )

    def eclipse(phase: float, pinch: float) -> list[tuple[float, float]]:
        return _stack(
            _rose(5, 0.62, 4, phase),
            _burst(20, 0.15, 0.45, phase, 0.06),
            _petals(10, 0.95, pinch, phase, 1.0),
            _ring(10, 0.93, 0.03, phase),
        )

    return {
        "lotus": lotus,
        "crown": crown,
        "drift_away": drift_away,
        "palace": palace,
        "sun_court": sun_court,
        "midnight": midnight,
        "saffron": saffron,
        "temple": temple,
        "moonflower": moonflower,
        "dahlia": dahlia,
        "peony": peony,
        "iris": iris,
        "camellia": camellia,
        "wisteria": wisteria,
        "orchid": orchid,
        "magnolia": magnolia,
        "star_lattice": star_lattice,
        "hex_tiling": hex_tiling,
        "compass": compass,
        "octagon": octagon,
        "diamond": diamond,
        "cathedral": cathedral,
        "whorl": whorl,
        "nautilus": nautilus,
        "fern": fern,
        "helix": helix,
        "spiral_bloom": spiral_bloom,
        "fibonacci": fibonacci,
        "tide": tide,
        "scallop": scallop,
        "ripple": ripple,
        "lace": lace,
        "silk": silk,
        "ring_tide": ring_tide,
        "nebula": nebula,
        "twin": twin,
        "orbit": orbit,
        "aurora": aurora,
        "comet": comet,
        "eclipse": eclipse,
    }


_COMPOSE = _compose_table()


GALLERY: tuple[GalleryDesign, ...] = (
    GalleryDesign("Twelve Fold Crown", "crown", "Mandalas"),
    GalleryDesign("Drift Away", "drift_away", "Mandalas"),
    GalleryDesign("Palace Lattice", "palace", "Mandalas"),
    GalleryDesign("Sun Court", "sun_court", "Mandalas"),
    GalleryDesign("Midnight Mandala", "midnight", "Mandalas"),
    GalleryDesign("Saffron Wheel", "saffron", "Mandalas"),
    GalleryDesign("Peony Weave", "peony", "Florals"),
    GalleryDesign("Iris Spiral", "iris", "Florals"),
    GalleryDesign("Camellia Rings", "camellia", "Florals"),
    GalleryDesign("Wisteria Curl", "wisteria", "Florals"),
    GalleryDesign("Orchid Star", "orchid", "Florals"),
    GalleryDesign("Magnolia", "magnolia", "Florals"),
    GalleryDesign("Star Lattice", "star_lattice", "Geometric"),
    GalleryDesign("Compass Rose", "compass", "Geometric"),
    GalleryDesign("Octagon Well", "octagon", "Geometric"),
    GalleryDesign("Cathedral Star", "cathedral", "Geometric"),
    GalleryDesign("Double Helix", "helix", "Spirals"),
    GalleryDesign("Spiral Bloom", "spiral_bloom", "Spirals"),
    GalleryDesign("Fibonacci Arms", "fibonacci", "Spirals"),
    GalleryDesign("Scalloped Tide", "scallop", "Waves"),
    GalleryDesign("Aurora Crown", "aurora", "Cosmic"),
    GalleryDesign("Comet Garden", "comet", "Cosmic"),
    GalleryDesign("Eclipse Rose", "eclipse", "Cosmic"),
    GalleryDesign("Cretan Labyrinth", "maze:labyrinth", "Mazes & Fills"),
    GalleryDesign("Ring Maze", "maze:ring-maze", "Mazes & Fills"),
    GalleryDesign("Random Maze", "maze:random", "Mazes & Fills"),
    GalleryDesign("Tight Maze", "maze:tight-maze", "Mazes & Fills"),
    GalleryDesign("Drift Maze", "maze:drift-maze", "Mazes & Fills"),
    GalleryDesign("Hilbert Fill", "maze:hilbert", "Mazes & Fills"),
    GalleryDesign("Fine Hilbert", "maze:fine-hilbert", "Mazes & Fills"),
    GalleryDesign("Peano Fill", "maze:peano", "Mazes & Fills"),
    *(
        GalleryDesign(name, f"sisyphus:{key}", "Sisyphus Classics")
        for name, key in CATALOG
    ),
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


def gallery_tile_slug(name: str) -> str:
    """The unique-id suffix for one gallery picture."""
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")


def retired_gallery_slugs(stored: set[str]) -> set[str]:
    """Picture slugs that are no longer in the gallery and should leave the registry."""
    current = {gallery_tile_slug(name) for name in gallery_names()}
    return {slug for slug in stored if slug not in current}


def gallery_names() -> list[str]:
    """Pleasant names, in display order."""
    return [design.name for design in GALLERY]


def gallery_categories() -> dict[str, str]:
    """Design name to category, in gallery order."""
    return {design.name: design.category for design in GALLERY}


def _kind(name: str) -> str:
    for design in GALLERY:
        if design.name == name:
            return design.kind
    raise PatternRejected(f"unknown gallery design {name}")


def trace_points(polar: list[tuple[float, float]], limit: int = 1600) -> list[list[float]]:
    """A short point list for the dashboard trace. This is not uploaded."""
    if len(polar) > limit:
        stride = math.ceil(len(polar) / limit)
        sampled = polar[::stride]
        if sampled[-1] != polar[-1]:
            sampled.append(polar[-1])
        polar = sampled
    return [[round(theta, 4), round(min(1.0, max(0.0, rho)), 4)] for theta, rho in polar]


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
