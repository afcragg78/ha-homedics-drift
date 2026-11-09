"""Space-filling paths that begin at the centre and end at the rim.

A gap is closed along the rim, or by a short spiral ramp. A straight radius
across open sand is not used as a join.
"""

from __future__ import annotations

import math
import random

from .patterns import densify

_RIM = 0.97


def _fit(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Cartesian polyline to a polar path. Crossing the centre does not sweep an arc."""
    polar: list[tuple[float, float]] = []
    previous = 0.0
    started = False
    for x, y in points:
        rho = math.hypot(x, y)
        if rho <= 1e-5:
            if not started:
                polar.append((0.0, 0.0))
                started = True
            else:
                polar.append((previous, 0.0))
            continue
        theta = math.atan2(y, x)
        if polar and polar[-1][1] == 0.0:
            # Leave the centre on this point's angle. Arriving used the old angle.
            if len(polar) == 1:
                polar[0] = (theta, 0.0)
            else:
                polar.append((theta, 0.0))
            previous = theta
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, min(_RIM, rho)))
        started = True
    if not polar:
        polar = [(0.0, 0.0)]
    if polar[0][1] != 0.0:
        polar.insert(0, (polar[0][0], 0.0))
    polar.append((polar[-1][0], 1.0))
    fitted = densify(polar, max_step=0.015)
    if len(fitted) > 16_000:
        fitted = densify(polar[::2], max_step=0.018)
    while len(fitted) < 800:
        fitted = densify(fitted, max_step=0.008)
        if len(fitted) > 5000:
            break
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return densify(fitted, max_step=0.015)


def _rim_arc(start: tuple[float, float], end: tuple[float, float], radius: float = _RIM) -> list[tuple[float, float]]:
    """Short way around the rim from start's angle to end's angle."""
    theta0 = math.atan2(start[1], start[0])
    theta1 = math.atan2(end[1], end[0])
    while theta1 - theta0 > math.pi:
        theta1 -= 2 * math.pi
    while theta1 - theta0 < -math.pi:
        theta1 += 2 * math.pi
    steps = max(2, int(abs(theta1 - theta0) / 0.04))
    arc = []
    for index in range(1, steps + 1):
        theta = theta0 + (theta1 - theta0) * index / steps
        arc.append((radius * math.cos(theta), radius * math.sin(theta)))
    return arc


def jigsaw(rings: int = 18, spiral_turns: float = 3.5) -> list[tuple[float, float]]:
    """Centre spiral, then rings. Each door is a short spiral ramp, not a radius."""
    path: list[tuple[float, float]] = [(0.0, 0.0)]
    steps = int(spiral_turns * 120)
    theta = 0.0
    for index in range(1, steps + 1):
        fraction = index / steps
        theta = spiral_turns * 2 * math.pi * fraction
        rho = 0.22 * fraction
        path.append((rho * math.cos(theta), rho * math.sin(theta)))
    rho = 0.22
    for ring in range(rings):
        outer = 0.22 + 0.74 * (ring + 1) / rings
        hold = int(150 * (0.86))
        ramp = 28
        for index in range(hold):
            theta += 2 * math.pi / (hold + ramp)
            path.append((rho * math.cos(theta), rho * math.sin(theta)))
        for index in range(1, ramp + 1):
            theta += 2 * math.pi / (hold + ramp)
            level = rho + (outer - rho) * index / ramp
            path.append((level * math.cos(theta), level * math.sin(theta)))
        rho = outer
    return _fit(path)


def labyrinth(circuits: int = 12) -> list[tuple[float, float]]:
    """Round labyrinth. Moving out to the next circuit happens while the ball is still turning."""
    path: list[tuple[float, float]] = [(0.0, 0.0)]
    theta = 0.0
    rho = 0.0
    for circuit in range(circuits):
        outer = 0.07 + 0.075 * circuit
        steps = 110
        for index in range(1, steps + 1):
            theta += (2 * math.pi * 0.92) / steps
            path.append((rho * math.cos(theta), rho * math.sin(theta)))
        ramp = 18
        for index in range(1, ramp + 1):
            theta += 0.5 / ramp
            level = rho + (outer - rho) * index / ramp
            path.append((level * math.cos(theta), level * math.sin(theta)))
        rho = outer
    return _fit(path)


def _maze_walk(size: int, seed: int) -> list[tuple[float, float]]:
    """Corridors of a round maze. The centre cell is exactly the origin, once."""
    rng = random.Random(seed)
    visited = [[False] * size for _ in range(size)]
    children: dict[tuple[int, int], list[tuple[int, int]]] = {}
    mid = size // 2
    stack = [(mid, mid)]
    visited[mid][mid] = True

    def inside(x: int, y: int) -> bool:
        cx = (x + 0.5) / size * 2 - 1
        cy = (y + 0.5) / size * 2 - 1
        return cx * cx + cy * cy <= 0.995

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
    span = 0.96

    def xy(x: int, y: int) -> tuple[float, float]:
        if (x, y) == (mid, mid):
            return (0.0, 0.0)
        return (((x + 0.5) / size) * 2 * span - span, span - ((y + 0.5) / size) * 2 * span)

    points = [xy(x, y) for x, y in walk]
    return _fit(points)


def hilbert(order: int = 5) -> list[tuple[float, float]]:
    """Hilbert curve. Where it would leave the disc, it runs along the rim instead."""
    raw: list[tuple[float, float]] = []

    def walk(level: int, x0: float, y0: float, xi: float, xj: float, yi: float, yj: float) -> None:
        if level == 0:
            raw.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
            return
        walk(level - 1, x0, y0, yi / 2, yj / 2, xi / 2, xj / 2)
        walk(level - 1, x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2)

    walk(order, -0.99, -0.99, 1.98, 0.0, 0.0, 1.98)
    limit = _RIM
    on_disc: list[tuple[float, float]] = []
    outside = False
    for x, y in raw:
        rho = math.hypot(x, y)
        if rho <= limit:
            if outside and on_disc:
                on_disc.extend(_rim_arc(on_disc[-1], (x, y), limit))
            on_disc.append((x, y))
            outside = False
        else:
            angle = math.atan2(y, x)
            point = (limit * math.cos(angle), limit * math.sin(angle))
            if not on_disc or math.hypot(point[0] - on_disc[-1][0], point[1] - on_disc[-1][1]) > 1e-4:
                on_disc.append(point)
            outside = True
    start = min(range(len(on_disc)), key=lambda index: math.hypot(*on_disc[index]))
    # From the centre sample out to the end of the curve, then back along the
    # same points to the other end. Reversed(on_disc) begins at the end, so
    # there is no jump from the end back to the centre.
    ordered = on_disc[start:] + list(reversed(on_disc))
    return _fit(ordered)


DESIGNS = {
    "jigsaw": lambda: jigsaw(18, 3.5),
    "labyrinth": lambda: labyrinth(12),
    "ring-maze": lambda: jigsaw(14, 2.2),
    "random": lambda: _maze_walk(17, 3),
    "tight-maze": lambda: _maze_walk(25, 11),
    "drift-maze": lambda: _maze_walk(21, 29),
    "hilbert": lambda: hilbert(5),
    "fine-hilbert": lambda: hilbert(6),
    "peano": lambda: hilbert(4),
}


def maze_polar(key: str) -> list[tuple[float, float]]:
    return DESIGNS[key]()
