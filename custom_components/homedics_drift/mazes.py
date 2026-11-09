"""Space-filling paths for the Mazes & Fills gallery.

Each design is one walk. A maze is traced by going down every corridor and
back, so the ball still follows a single line. Fills are clipped to the disc
and joined along the rim instead of cutting across.
"""

from __future__ import annotations

import math
import random

from .patterns import densify


def _finish(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 2:
        points = [(0.0, 0.0), (0.2, 0.2), (1.0, 0.5)]
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        rho = min(0.96, math.hypot(x, y))
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, rho))
    polar = [(polar[0][0], 0.0), *polar, (polar[-1][0], 1.0)]
    fitted = densify(polar, max_step=0.018)
    if len(fitted) > 16_000:
        fitted = densify(polar[::2], max_step=0.02)
    while len(fitted) < 800:
        fitted = densify(fitted, max_step=0.01)
        if len(fitted) > 2000:
            break
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return fitted


def _xy(polar_like: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(rho * math.cos(theta), rho * math.sin(theta)) for theta, rho in polar_like]


def jigsaw(rings: int = 14, spiral_turns: float = 3.0) -> list[tuple[float, float]]:
    """Rings with one door each, and a spiral in the middle."""
    path: list[tuple[float, float]] = []
    steps = int(spiral_turns * 80)
    for index in range(steps + 1):
        fraction = index / steps
        theta = spiral_turns * 2 * math.pi * fraction
        rho = 0.02 + 0.2 * fraction
        path.append((rho * math.cos(theta), rho * math.sin(theta)))
    for ring in range(rings):
        radius = 0.26 + (0.7 * ring / max(1, rings - 1))
        gap = (ring * 2.3) % (2 * math.pi)
        steps = 90
        for index in range(steps + 1):
            theta = gap + 0.35 + (2 * math.pi - 0.55) * index / steps
            path.append((radius * math.cos(theta), radius * math.sin(theta)))
        door = gap + 0.15
        path.append((radius * math.cos(door), radius * math.sin(door)))
    return _finish(path)


def labyrinth(circuits: int = 8) -> list[tuple[float, float]]:
    """A round labyrinth: each circuit is a long arc into the next door."""
    path: list[tuple[float, float]] = [(0.0, 0.0)]
    for circuit in range(circuits):
        radius = 0.12 + 0.1 * circuit
        start = (circuit % 2) * math.pi
        steps = 70
        for index in range(steps + 1):
            theta = start + (2 * math.pi - 0.4) * index / steps
            path.append((radius * math.cos(theta), radius * math.sin(theta)))
    return _finish(path)


def _maze_cells(size: int, seed: int) -> list[tuple[int, int]]:
    """Recursive-backtracker spanning tree, then a there-and-back walk."""
    rng = random.Random(seed)
    visited = [[False] * size for _ in range(size)]
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    stack = [(size // 2, size // 2)]
    visited[size // 2][size // 2] = True

    def inside(x: int, y: int) -> bool:
        cx = (x + 0.5) / size * 2 - 1
        cy = (y + 0.5) / size * 2 - 1
        return cx * cx + cy * cy <= 0.82

    while stack:
        x, y = stack[-1]
        options = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < size and 0 <= ny < size and inside(nx, ny) and not visited[ny][nx]:
                options.append((nx, ny))
        if not options:
            stack.pop()
            continue
        nx, ny = rng.choice(options)
        visited[ny][nx] = True
        parent[(nx, ny)] = (x, y)
        stack.append((nx, ny))
    children: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for child, origin in parent.items():
        children.setdefault(origin, []).append(child)
    walk: list[tuple[int, int]] = []

    def dfs(cell: tuple[int, int]) -> None:
        walk.append(cell)
        for child in children.get(cell, []):
            dfs(child)
            walk.append(cell)

    dfs((size // 2, size // 2))
    points = []
    for x, y in walk:
        px = ((x + 0.5) / size) * 1.7 - 0.85
        py = 0.85 - ((y + 0.5) / size) * 1.7
        points.append((px, py))
    return _finish(points)


def hilbert(order: int = 5) -> list[tuple[float, float]]:
    """A Hilbert curve, kept inside the disc and joined along the rim."""
    points: list[tuple[float, float]] = []

    def walk(level: int, x0: float, y0: float, xi: float, xj: float, yi: float, yj: float) -> None:
        if level == 0:
            points.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
            return
        walk(level - 1, x0, y0, yi / 2, yj / 2, xi / 2, xj / 2)
        walk(level - 1, x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2)

    walk(order, -0.86, -0.86, 1.72, 0, 0, 1.72)
    kept: list[tuple[float, float]] = []
    for x, y in points:
        if math.hypot(x, y) <= 0.94:
            kept.append((x, y))
        elif kept:
            angle = math.atan2(y, x)
            kept.append((0.94 * math.cos(angle), 0.94 * math.sin(angle)))
    return _finish(kept)


def square_spiral(turns: int = 18) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    x = y = 0.0
    step = 0.08
    for index in range(turns * 4):
        length = step * (index // 2 + 1)
        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[index % 4]
        samples = max(2, int(length / 0.02))
        for sample in range(1, samples + 1):
            path.append((x + dx * length * sample / samples, y + dy * length * sample / samples))
        x += dx * length
        y += dy * length
        if math.hypot(x, y) > 0.9:
            break
    return _finish([(min(0.9, max(-0.9, px)), min(0.9, max(-0.9, py))) for px, py in path])


def meander(bands: int = 16) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    for band in range(bands):
        y = -0.82 + 1.64 * band / max(1, bands - 1)
        xs = [i / 40 for i in range(41)]
        if band % 2:
            xs.reverse()
        for x in xs:
            px = -0.82 + 1.64 * x
            if px * px + y * y <= 0.9:
                path.append((px, y + 0.03 * math.sin(px * 18)))
    return _finish(path)


def cross_fill(step: float = 0.07) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    count = int(1.7 / step)
    for row in range(count):
        y = -0.85 + row * step
        cols = range(count) if row % 2 == 0 else range(count - 1, -1, -1)
        for col in cols:
            x = -0.85 + col * step
            if x * x + y * y <= 0.88:
                path.append((x, y))
    return _finish(path)


DESIGNS = {
    "jigsaw": lambda: jigsaw(16, 3.2),
    "labyrinth": lambda: labyrinth(9),
    "ring-maze": lambda: jigsaw(11, 2.0),
    "random": lambda: _maze_cells(13, 3),
    "tight-maze": lambda: _maze_cells(17, 11),
    "drift-maze": lambda: _maze_cells(15, 29),
    "hilbert": lambda: hilbert(5),
    "fine-hilbert": lambda: hilbert(6),
    "peano": lambda: hilbert(4),
    "square-spiral": square_spiral,
    "meander": meander,
    "cross": cross_fill,
}


def maze_polar(key: str) -> list[tuple[float, float]]:
    builder = DESIGNS[key]
    return builder()
