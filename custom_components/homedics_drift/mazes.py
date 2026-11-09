"""Space-filling paths that begin at the centre and end at the rim.

Turns happen on the path itself or on the rim. Nothing cuts straight across
the disc to close a gap.
"""

from __future__ import annotations

import math
import random

from .patterns import densify


def _fit(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Polar path. The first point is the centre; the last sits on the rim."""
    if math.hypot(*points[0]) > 0.02:
        points = [(0.0, 0.0), *points]
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        rho = min(0.97, math.hypot(x, y))
        if rho <= 1e-6:
            polar.append((previous, 0.0))
            continue
        theta = math.atan2(y, x)
        if polar and polar[-1][1] == 0.0 and len(polar) == 1:
            # The centre uses the first real angle, so the opening is a ray
            # along the path rather than a semicircle sweep.
            polar[0] = (theta, 0.0)
            previous = theta
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, rho))
    # A short step outward on the same angle, not a new chord.
    polar.append((polar[-1][0], 1.0))
    fitted = densify(polar, max_step=0.016)
    if len(fitted) > 16_000:
        fitted = densify(polar[::2], max_step=0.018)
    while len(fitted) < 800:
        fitted = densify(fitted, max_step=0.008)
        if len(fitted) > 4000:
            break
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return densify(fitted, max_step=0.016)


def jigsaw(rings: int = 18, spiral_turns: float = 4.0) -> list[tuple[float, float]]:
    """A centre spiral, then rings out to the rim. Doors are one spacing wide."""
    path: list[tuple[float, float]] = []
    steps = int(spiral_turns * 100)
    for index in range(steps + 1):
        fraction = index / steps
        theta = spiral_turns * 2 * math.pi * fraction
        rho = 0.012 * fraction + 0.22 * fraction
        path.append((rho * math.cos(theta), rho * math.sin(theta)))
    gap = (spiral_turns * 2 * math.pi) % (2 * math.pi)
    for ring in range(rings):
        inner = 0.24 + (0.72 * ring / rings)
        outer = 0.24 + (0.72 * (ring + 1) / rings)
        radius = inner
        sweep_start = gap + 0.25
        sweep = 2 * math.pi - 0.4
        steps = 120
        for index in range(steps + 1):
            theta = sweep_start + sweep * index / steps
            path.append((radius * math.cos(theta), radius * math.sin(theta)))
        # Step out through the door to the next ring. This is the wall opening.
        door = sweep_start + sweep
        path.append((outer * math.cos(door), outer * math.sin(door)))
        gap = door
    return _fit(path)


def labyrinth(circuits: int = 11) -> list[tuple[float, float]]:
    """Round labyrinth grown from the centre to the rim."""
    path: list[tuple[float, float]] = [(0.0, 0.0)]
    for circuit in range(circuits):
        radius = 0.08 + 0.08 * circuit
        start = path[-1]
        angle = math.atan2(start[1], start[0]) if circuit else 0.0
        steps = 100
        for index in range(1, steps + 1):
            theta = angle + (2 * math.pi - 0.35) * index / steps
            path.append((radius * math.cos(theta), radius * math.sin(theta)))
        end = path[-1]
        nxt = min(0.96, radius + 0.08)
        path.append((nxt * math.cos(math.atan2(end[1], end[0])), nxt * math.sin(math.atan2(end[1], end[0]))))
    return _fit(path)


def _maze_walk(size: int, seed: int) -> list[tuple[float, float]]:
    """Every corridor of a round maze, walked out and back from the centre."""
    rng = random.Random(seed)
    visited = [[False] * size for _ in range(size)]
    children: dict[tuple[int, int], list[tuple[int, int]]] = {}
    mid = size // 2
    stack = [(mid, mid)]
    visited[mid][mid] = True

    def inside(x: int, y: int) -> bool:
        cx = (x + 0.5) / size * 2 - 1
        cy = (y + 0.5) / size * 2 - 1
        return cx * cx + cy * cy <= 0.98

    while stack:
        x, y = stack[-1]
        options = [
            (x + dx, y + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= x + dx < size and 0 <= y + dy < size and inside(x + dx, y + dy) and not visited[y + dy][x + dx]
        ]
        if not options:
            stack.pop()
            continue
        nx, ny = rng.choice(options)
        visited[ny][nx] = True
        children.setdefault((x, y), []).append((nx, ny))
        stack.append((nx, ny))
    walk: list[tuple[int, int]] = []

    def dfs(cell: tuple[int, int]) -> None:
        walk.append(cell)
        for child in children.get(cell, []):
            dfs(child)
            walk.append(cell)

    dfs((mid, mid))
    points = [(0.0, 0.0)]
    span = 0.96
    for x, y in walk:
        points.append((((x + 0.5) / size) * 2 * span - span, span - ((y + 0.5) / size) * 2 * span))
    return _fit(points)


def hilbert(order: int = 5) -> list[tuple[float, float]]:
    """Hilbert curve clipped to the disc, started at the sample nearest the centre."""
    raw: list[tuple[float, float]] = []

    def walk(level: int, x0: float, y0: float, xi: float, xj: float, yi: float, yj: float) -> None:
        if level == 0:
            raw.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
            return
        walk(level - 1, x0, y0, yi / 2, yj / 2, xi / 2, xj / 2)
        walk(level - 1, x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2)

    walk(order, -0.96, -0.96, 1.92, 0, 0, 1.92)
    kept = [(x, y) for x, y in raw if math.hypot(x, y) <= 0.96]
    if not kept:
        return _fit([(0.0, 0.0), (0.2, 0.0)])
    start = min(range(len(kept)), key=lambda index: math.hypot(*kept[index]))
    # Forward to the end, then back along the same curve to the other end.
    # The return trip sits in the groove that was just drawn.
    ordered = kept[start:] + list(reversed(kept[: start + 1]))
    return _fit(ordered)


def meander(bands: int = 26) -> list[tuple[float, float]]:
    """Rows that turn on the rim, starting on the centre row."""
    path = [(0.0, 0.0)]
    step = 1.84 / bands
    ys: list[float] = []
    y = step
    while y < 0.9:
        ys.extend((y, -y))
        y += step
    for index, row in enumerate(ys):
        half = math.sqrt(max(0.0, 0.94**2 - row * row))
        if index == 0:
            path.append((0.0, row))
        going_right = index % 2 == 0
        start_x, end_x = (-half, half) if going_right else (half, -half)
        samples = 48
        for sample in range(samples + 1):
            x = start_x + (end_x - start_x) * sample / samples
            path.append((x, row))
    return _fit(path)


DESIGNS = {
    "jigsaw": lambda: jigsaw(18, 4.0),
    "labyrinth": lambda: labyrinth(12),
    "ring-maze": lambda: jigsaw(12, 2.4),
    "random": lambda: _maze_walk(17, 3),
    "tight-maze": lambda: _maze_walk(25, 11),
    "drift-maze": lambda: _maze_walk(21, 29),
    "hilbert": lambda: hilbert(5),
    "fine-hilbert": lambda: hilbert(6),
    "peano": lambda: hilbert(4),
    "meander": meander,
}


def maze_polar(key: str) -> list[tuple[float, float]]:
    return DESIGNS[key]()
