"""Single-line mazes and fills.

Every join is a corridor: an orthogonal step, a circular circuit, or a short
door one ring wide. A radius across open sand is not used to finish a path.
Straight runs are sampled in Cartesian space first, so the table's polar
interpolation cannot bow them into diagonals.
"""

from __future__ import annotations

import math
import random

from .patterns import densify

_LIMIT = 0.97


def _polyline(points: list[tuple[float, float]], step: float = 0.01) -> list[tuple[float, float]]:
    """Even Cartesian samples. Polar interpolation of these stays on the line."""
    if not points:
        return []
    out = [points[0]]
    for x, y in points[1:]:
        x0, y0 = out[-1]
        dist = math.hypot(x - x0, y - y0)
        count = max(1, math.ceil(dist / step))
        for index in range(1, count + 1):
            fraction = index / count
            out.append((x0 + (x - x0) * fraction, y0 + (y - y0) * fraction))
    return out


def _inside(x: float, y: float, limit: float = _LIMIT) -> bool:
    return x * x + y * y <= limit * limit


def _axis_link(
    start: tuple[float, float],
    end: tuple[float, float],
    limit: float = _LIMIT,
) -> list[tuple[float, float]]:
    """One right-angle join that stays in the disc. Falls back to a short stair."""
    if math.hypot(end[0] - start[0], end[1] - start[1]) < 1e-4:
        return []
    corners = ((end[0], start[1]), (start[0], end[1]))
    for corner in corners:
        if corner == start or corner == end:
            continue
        if _inside(corner[0], corner[1], limit):
            return [corner]
    step = 0.02
    x, y = start
    stair: list[tuple[float, float]] = []
    for _ in range(400):
        if math.hypot(end[0] - x, end[1] - y) <= step:
            break
        options: list[tuple[float, float]] = []
        for dx, dy in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
            nx, ny = x + dx, y + dy
            if not _inside(nx, ny, limit):
                continue
            if math.hypot(end[0] - nx, end[1] - ny) < math.hypot(end[0] - x, end[1] - y) - 1e-6:
                options.append((nx, ny))
        if not options:
            break
        x, y = min(options, key=lambda point: math.hypot(end[0] - point[0], end[1] - point[1]))
        stair.append((x, y))
    return stair


def _extend_to_rim(points: list[tuple[float, float]], radius: float = 0.992) -> list[tuple[float, float]]:
    """Continue the last corridor until it meets the rim. Does not aim at the centre."""
    if len(points) < 2:
        return points
    x0, y0 = points[-2]
    x1, y1 = points[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return points
    dx /= length
    dy /= length
    if x1 * dx + y1 * dy < 0:
        dx, dy = -dx, -dy
    x, y = x1, y1
    extra: list[tuple[float, float]] = []
    if math.hypot(x, y) >= radius:
        return points
    for _ in range(200):
        x += dx * 0.01
        y += dy * 0.01
        if not _inside(x, y, 1.0):
            break
        extra.append((x, y))
        if math.hypot(x, y) >= radius:
            break
    return points + extra


def _fit(points: list[tuple[float, float]], step: float = 0.01, polar_step: float = 0.012) -> list[tuple[float, float]]:
    """Cartesian corridors to a polar path that still starts at the centre and ends at the rim."""
    if not points:
        points = [(0.0, 0.0), (0.01, 0.0)]
    if math.hypot(*points[0]) > 1e-4:
        x, y = points[0]
        points = [(0.0, 0.0), (x, 0.0), (x, y), *points[1:]]
    points = _extend_to_rim(points)
    sampled = _polyline(points, step)
    polar = _to_polar(sampled, polar_step)
    # Stored points have to stay coarse enough that the table's 0.01 densify still fits.
    while len(polar) > 16_000 and polar_step < 0.022:
        polar_step *= 1.2
        step = max(step, polar_step)
        sampled = _polyline(points, step)
        polar = _to_polar(sampled, polar_step)
    return polar


def _to_polar(points: list[tuple[float, float]], polar_step: float = 0.012) -> list[tuple[float, float]]:
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        rho = math.hypot(x, y)
        if rho <= 1e-5:
            if not polar:
                polar.append((0.0, 0.0))
            else:
                polar.append((previous, 0.0))
            continue
        theta = math.atan2(y, x)
        if polar and polar[-1][1] == 0.0:
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
        polar.append((theta, min(0.998, rho)))
    if not polar:
        polar = [(0.0, 0.0)]
    if polar[0][1] != 0.0:
        polar.insert(0, (polar[0][0], 0.0))
    if polar[-1][1] < 1.0:
        polar.append((polar[-1][0], 1.0))
    fitted = densify(polar, max_step=polar_step)
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return densify(fitted, max_step=polar_step)


def cretan() -> list[tuple[float, float]]:
    """Classical seven-circuit labyrinth.

    Circuits are numbered from the outside. From the centre the walk reverses
    the entry sequence 3-2-1-4-7-6-5. Each circuit stops at a gap on the
    bottom axis and turns back, so the rings are not closed circles and the
    joins are not one spoke through them.
    """
    # Level 7 is the innermost circuit, level 1 the outermost.
    order = (5, 6, 7, 4, 1, 2, 3)
    spacing = (0.88 - 0.16) / 6

    def radius(level: int) -> float:
        return 0.16 + (7 - level) * spacing

    axis = -math.pi / 2
    gap = 0.22
    path: list[tuple[float, float]] = [(0.0, 0.0)]
    direction = 1
    # Start on one lip of the bottom gap. The long arc lands on the other lip,
    # so the opening stays put instead of wandering into an empty wedge.
    angle = axis + direction * gap / 2
    for index, level in enumerate(order):
        radius_now = radius(level)
        path.append((radius_now * math.cos(angle), radius_now * math.sin(angle)))
        sweep = direction * (2 * math.pi - gap)
        steps = 220
        for step in range(1, steps + 1):
            theta = angle + sweep * step / steps
            path.append((radius_now * math.cos(theta), radius_now * math.sin(theta)))
        angle += sweep
        direction *= -1
    path.append((0.992 * math.cos(angle), 0.992 * math.sin(angle)))
    return _fit(path)


def ring_maze(rings: int = 12) -> list[tuple[float, float]]:
    """Concentric circuits that reverse. Each door is one ring wide, and every ring is drawn."""
    path: list[tuple[float, float]] = [(0.0, 0.0)]
    theta = 0.4
    direction = 1.0
    for index in range(rings):
        outer = 0.08 + 0.88 * (index + 1) / rings
        path.append((outer * math.cos(theta), outer * math.sin(theta)))
        # A little more than a full turn covers the ring and moves the next door.
        sweep = direction * (2 * math.pi + 0.62)
        steps = 170 + index * 8
        for step in range(1, steps + 1):
            angle = theta + sweep * step / steps
            path.append((outer * math.cos(angle), outer * math.sin(angle)))
        theta += sweep
        direction *= -1
    path.append((0.992 * math.cos(theta), 0.992 * math.sin(theta)))
    return _fit(path)


def _maze_walk(size: int, seed: int) -> list[tuple[float, float]]:
    """A round orthogonal maze. The walk leaves along a corridor, not across a radius."""
    rng = random.Random(seed)
    visited = [[False] * size for _ in range(size)]
    children: dict[tuple[int, int], list[tuple[int, int]]] = {}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
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
        parent[(nx, ny)] = (x, y)
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
        return (((x + 0.5) / size) * 2 * span - span, span - ((y + 0.5) / size) * 2 * span)

    # The depth-first walk finishes where it started. Follow the tree back out
    # to a rim cell so the ending stroke stays on corridors.
    cells = [cell for cell, flag in (((x, y), visited[y][x]) for y in range(size) for x in range(size)) if flag]
    goal = max(cells, key=lambda cell: math.hypot(*xy(*cell)))
    chain: list[tuple[int, int]] = []
    cell = goal
    while cell != (mid, mid):
        chain.append(cell)
        cell = parent[cell]
    chain.reverse()
    walk.extend(chain)
    return _fit([xy(x, y) for x, y in walk])


def _hilbert_points(order: int) -> list[tuple[float, float]]:
    raw: list[tuple[float, float]] = []

    def walk(level: int, x0: float, y0: float, xi: float, xj: float, yi: float, yj: float) -> None:
        if level == 0:
            raw.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
            return
        walk(level - 1, x0, y0, yi / 2, yj / 2, xi / 2, xj / 2)
        walk(level - 1, x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
        walk(level - 1, x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2)

    span = 0.96
    walk(order, -span, -span, 2 * span, 0.0, 0.0, 2 * span)
    cell = 2 * span / (2**order)
    kept: list[tuple[float, float]] = []
    previous: tuple[float, float] | None = None
    for x, y in raw:
        if not _inside(x, y):
            continue
        if previous is not None and math.hypot(x - previous[0], y - previous[1]) > cell * 1.6:
            kept.extend(_axis_link(previous, (x, y)))
        kept.append((x, y))
        previous = (x, y)
    start = min(range(len(kept)), key=lambda index: math.hypot(*kept[index]))
    # Out to one end, then back along the same points and on to the other end.
    return kept[start:] + list(reversed(kept))


def hilbert(order: int = 5) -> list[tuple[float, float]]:
    """Hilbert curve clipped to the disc with right-angle joins."""
    return _fit(_hilbert_points(order))


DESIGNS = {
    "labyrinth": cretan,
    "ring-maze": ring_maze,
    "random": lambda: _maze_walk(17, 3),
    "tight-maze": lambda: _maze_walk(25, 11),
    "drift-maze": lambda: _maze_walk(21, 29),
    "hilbert": lambda: hilbert(5),
    "fine-hilbert": lambda: hilbert(6),
    "peano": lambda: hilbert(4),
}


def maze_polar(key: str) -> list[tuple[float, float]]:
    return DESIGNS[key]()
