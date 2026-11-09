"""Picture to sand: a subject outline, then echo contours that fill the disc.

Pillow reads an uploaded photo. The rest is a small grid: threshold the ink,
measure distance from it, and trace those distances as one continuous path.
Spacing stays coarse enough for the Drift ball and short enough to upload.
"""

from __future__ import annotations

import io
import math

from .patterns import MAX_POINTS, PatternRejected, densify, parse_thr

STYLE_CONTOURS = "contours"
STYLE_LINE = "line"
ART_STYLES = (STYLE_CONTOURS, STYLE_LINE)

_GRID = 72


def normalize_art_style(value: object) -> str:
    """Contours unless the caller asked for a plain line drawing."""
    if isinstance(value, str) and value.strip().lower() in ("line", "line drawing", "lines"):
        return STYLE_LINE
    return STYLE_CONTOURS


def grid_from_image(data: bytes, size: int = _GRID) -> list[list[float]]:
    """Darkness from 0 (paper) to 1 (ink), outside the disc cleared."""
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("L").resize((size, size), Image.Resampling.BOX)
    samples = list(image.tobytes())
    low = min(samples)
    high = max(samples)
    span = max(1, high - low)
    grid: list[list[float]] = []
    for y in range(size):
        row: list[float] = []
        for x in range(size):
            shade = 1.0 - (samples[y * size + x] - low) / span
            nx = (x / (size - 1)) * 2 - 1
            ny = 1 - (y / (size - 1)) * 2
            if math.hypot(nx, ny) > 1:
                shade = 0.0
            row.append(shade)
        grid.append(row)
    return grid


def _raster(strokes: list[list[tuple[float, float]]], size: int = _GRID) -> list[list[bool]]:
    """Paint line art into a disc mask. Coordinates are -1..1."""
    ink = [[False] * size for _ in range(size)]

    def plot(x: float, y: float) -> None:
        if math.hypot(x, y) > 0.98:
            return
        gx = int(round((x + 1) / 2 * (size - 1)))
        gy = int(round((1 - y) / 2 * (size - 1)))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx, yy = gx + dx, gy + dy
                if 0 <= xx < size and 0 <= yy < size:
                    ink[yy][xx] = True

    for stroke in strokes:
        if len(stroke) < 2:
            continue
        for (x0, y0), (x1, y1) in zip(stroke, stroke[1:], strict=False):
            steps = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.012))
            for index in range(steps + 1):
                unit = index / steps
                plot(x0 + (x1 - x0) * unit, y0 + (y1 - y0) * unit)
    return ink


def _distance(ink: list[list[bool]]) -> list[list[float]]:
    """Chamfer distance from the ink, in disc units."""
    size = len(ink)
    inf = 1e6
    dist = [[0.0 if ink[y][x] else inf for x in range(size)] for y in range(size)]
    ortho, diag = 1.0, 1.414
    for y in range(size):
        for x in range(size):
            best = dist[y][x]
            if y:
                best = min(best, dist[y - 1][x] + ortho)
            if x:
                best = min(best, dist[y][x - 1] + ortho)
            if y and x:
                best = min(best, dist[y - 1][x - 1] + diag)
            if y and x + 1 < size:
                best = min(best, dist[y - 1][x + 1] + diag)
            dist[y][x] = best
    for y in range(size - 1, -1, -1):
        for x in range(size - 1, -1, -1):
            best = dist[y][x]
            if y + 1 < size:
                best = min(best, dist[y + 1][x] + ortho)
            if x + 1 < size:
                best = min(best, dist[y][x + 1] + ortho)
            if y + 1 < size and x + 1 < size:
                best = min(best, dist[y + 1][x + 1] + diag)
            if y + 1 < size and x:
                best = min(best, dist[y + 1][x - 1] + diag)
            dist[y][x] = best
    scale = 2.0 / size
    return [[value * scale for value in row] for row in dist]


def _cell(size: int, x: int, y: int) -> tuple[float, float]:
    return ((x / (size - 1)) * 2 - 1, 1 - (y / (size - 1)) * 2)


def _edge(grid: list[list[float]], x: int, y: int, edge: int, level: float) -> tuple[float, float]:
    size = len(grid)

    def lerp(v0: float, v1: float, p0: tuple[float, float], p1: tuple[float, float]) -> tuple[float, float]:
        span = v1 - v0
        t = 0.5 if abs(span) < 1e-9 else min(1.0, max(0.0, (level - v0) / span))
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

    if edge == 0:
        return lerp(grid[y][x], grid[y][x + 1], _cell(size, x, y), _cell(size, x + 1, y))
    if edge == 1:
        return lerp(grid[y][x + 1], grid[y + 1][x + 1], _cell(size, x + 1, y), _cell(size, x + 1, y + 1))
    if edge == 2:
        return lerp(grid[y + 1][x], grid[y + 1][x + 1], _cell(size, x, y + 1), _cell(size, x + 1, y + 1))
    return lerp(grid[y][x], grid[y + 1][x], _cell(size, x, y), _cell(size, x, y + 1))


_CASES: dict[int, tuple[tuple[int, int], ...]] = {
    0: (),
    1: ((0, 3),),
    2: ((0, 1),),
    3: ((1, 3),),
    4: ((1, 2),),
    5: ((0, 3), (1, 2)),
    6: ((0, 2),),
    7: ((2, 3),),
    8: ((2, 3),),
    9: ((0, 2),),
    10: ((0, 1), (2, 3)),
    11: ((1, 2),),
    12: ((1, 3),),
    13: ((0, 1),),
    14: ((0, 3),),
    15: (),
}


def _chains(segments: list[tuple[tuple[float, float], tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    def key(point: tuple[float, float]) -> tuple[int, int]:
        return (round(point[0] * 40), round(point[1] * 40))

    adjacency: dict[tuple[int, int], list[int]] = {}
    for index, (start, end) in enumerate(segments):
        adjacency.setdefault(key(start), []).append(index)
        adjacency.setdefault(key(end), []).append(index)
    used = [False] * len(segments)

    def walk(start_index: int, current: tuple[int, int]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        previous = start_index
        while True:
            nxt = next((i for i in adjacency.get(current, []) if i != previous and not used[i]), None)
            if nxt is None:
                break
            used[nxt] = True
            start, end = segments[nxt]
            if key(start) == current:
                points.append(end)
                current = key(end)
            else:
                points.append(start)
                current = key(start)
            previous = nxt
        return points

    chains: list[list[tuple[float, float]]] = []
    for index, (start, end) in enumerate(segments):
        if used[index]:
            continue
        used[index] = True
        backward = walk(index, key(start))
        forward = walk(index, key(end))
        chain = [*reversed(backward), start, end, *forward]
        if len(chain) >= 4:
            chains.append(chain)
    return chains


def _iso(grid: list[list[float]], level: float) -> list[list[tuple[float, float]]]:
    size = len(grid)
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for y in range(size - 1):
        for x in range(size - 1):
            nx = (x + 0.5) / (size - 1) * 2 - 1
            ny = 1 - (y + 0.5) / (size - 1) * 2
            if math.hypot(nx, ny) > 0.98:
                continue
            index = (
                (grid[y][x] >= level)
                + 2 * (grid[y][x + 1] >= level)
                + 4 * (grid[y + 1][x + 1] >= level)
                + 8 * (grid[y + 1][x] >= level)
            )
            for left, right in _CASES[index]:
                start = _edge(grid, x, y, left, level)
                end = _edge(grid, x, y, right, level)
                if math.hypot(*start) > 0.98 and math.hypot(*end) > 0.98:
                    continue
                segments.append((start, end))
    return _chains(segments)


def _bridge(path: list[tuple[float, float]], chain: list[tuple[float, float]]) -> list[tuple[float, float]]:
    x0, y0 = path[-1]
    x1, y1 = chain[0]
    if math.hypot(x1 - x0, y1 - y0) <= 0.04:
        return [*path, *chain]
    theta0, rho0 = math.atan2(y0, x0), min(0.96, math.hypot(x0, y0))
    theta1, rho1 = math.atan2(y1, x1), min(0.96, math.hypot(x1, y1))
    while theta1 - theta0 > math.pi:
        theta1 -= 2 * math.pi
    while theta1 - theta0 < -math.pi:
        theta1 += 2 * math.pi
    ring = max(rho0, rho1, 0.08)
    bridge: list[tuple[float, float]] = []
    for index in range(1, 5):
        rho = rho0 + (ring - rho0) * index / 4
        bridge.append((rho * math.cos(theta0), rho * math.sin(theta0)))
    steps = max(2, int(abs(theta1 - theta0) / 0.08))
    for index in range(1, steps + 1):
        theta = theta0 + (theta1 - theta0) * index / steps
        bridge.append((ring * math.cos(theta), ring * math.sin(theta)))
    for index in range(1, 5):
        rho = ring + (rho1 - ring) * index / 4
        bridge.append((rho * math.cos(theta1), rho * math.sin(theta1)))
    return [*path, *bridge, *chain]


def _join(chains: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    ordered = sorted(chains, key=lambda chain: sum(math.hypot(x, y) for x, y in chain) / len(chain))
    path: list[tuple[float, float]] = []
    for chain in ordered:
        path = chain if not path else _bridge(path, chain)
    if len(path) < 2:
        raise PatternRejected("That picture did not contain a shape")
    return path


def contour_xy(ink: list[list[bool]], *, echoes: bool) -> list[tuple[float, float]]:
    """Subject outline, and when echoes is set, distance rings out to the rim."""
    if not any(cell for row in ink for cell in row):
        raise PatternRejected("That picture did not contain a shape")
    dist = _distance(ink)
    chains = _iso(dist, 0.02)
    if echoes:
        level = 0.06
        while level < 0.92:
            chains.extend(_iso(dist, level))
            level += 0.055
    if not chains:
        raise PatternRejected("That picture did not contain a shape")
    return _join(chains)


def engraving_polar(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """One centre-to-rim path the ball can follow."""
    polar: list[tuple[float, float]] = []
    previous = 0.0
    kept = [points[0]]
    for point in points[1:]:
        if math.hypot(point[0] - kept[-1][0], point[1] - kept[-1][1]) >= 0.018:
            kept.append(point)
    for x, y in kept:
        rho = min(0.97, math.hypot(x, y))
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, rho))
    polar = [(polar[0][0], 0.0), *polar, (polar[-1][0], 1.0)]
    step = 0.02
    fitted = densify(polar, max_step=step)
    while len(fitted) > 14_000 and step < 0.05:
        step *= 1.25
        fitted = densify(polar, max_step=step)
    while len(fitted) < 800 and step > 0.006:
        step *= 0.75
        fitted = densify(polar, max_step=step)
    if len(fitted) > MAX_POINTS:
        stride = math.ceil(len(fitted) / 12_000)
        fitted = densify(fitted[::stride], max_step=0.02)
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return fitted


def thr_from_xy(points: list[tuple[float, float]]) -> str:
    polar = engraving_polar(points)
    return "".join(f"{theta:.6f} {rho:.6f}\n" for theta, rho in polar)


def art_from_image(data: bytes, style: object) -> str:
    """Contours or a single outline from a photo."""
    grid = grid_from_image(data)
    ink = [[cell >= 0.45 for cell in row] for row in grid]
    return thr_from_xy(contour_xy(ink, echoes=normalize_art_style(style) == STYLE_CONTOURS))


def art_from_points(points: list[tuple[float, float]], style: object) -> str:
    """Wrap a model's line in echo contours, or keep the line itself."""
    ink = _raster([points])
    if not any(cell for row in ink for cell in row):
        raise PatternRejected("The drawing needs at least two points")
    return thr_from_xy(contour_xy(ink, echoes=normalize_art_style(style) == STYLE_CONTOURS))


def xy_from_thr(text: str) -> list[tuple[float, float]]:
    return [(rho * math.cos(theta), rho * math.sin(theta)) for theta, rho in parse_thr(text)]


def _arc(cx: float, cy: float, radius: float, start: float, sweep: float, steps: int = 24) -> list[tuple[float, float]]:
    return [
        (cx + radius * math.cos(start + sweep * index / steps), cy + radius * math.sin(start + sweep * index / steps))
        for index in range(steps + 1)
    ]


def study_strokes(name: str) -> list[list[tuple[float, float]]]:
    """Original line art. These are not copies of anyone's characters."""
    key = name.lower()
    if key == "tiger":
        return [
            _arc(0, 0.05, 0.42, 0.2, 5.8, 36),
            _arc(-0.28, 0.42, 0.16, 0.4, 2.4, 16),
            _arc(0.28, 0.42, 0.16, 0.3, 2.4, 16),
            _arc(-0.16, 0.08, 0.07, 0, 6.2, 12),
            _arc(0.16, 0.08, 0.07, 0, 6.2, 12),
            [(0, -0.02), (0, -0.16), (-0.06, -0.22), (0.06, -0.22), (0, -0.16)],
            _arc(0, 0.02, 0.34, 3.5, 2.4, 18),
            _arc(0, -0.02, 0.5, 3.6, 2.2, 16),
        ]
    if key == "koi":
        body = _arc(0.05, 0, 0.28, 0.4, 5.4, 28)
        return [
            body,
            [(0.28, 0.08), (0.55, 0.28), (0.42, 0.0), (0.55, -0.28), (0.28, -0.08)],
            _arc(-0.05, 0.08, 0.05, 0, 6.2, 10),
            _arc(0.0, 0.16, 0.18, 0.6, 2.2, 12),
            _arc(0.0, -0.16, 0.18, 3.8, 2.2, 12),
        ]
    if key == "lotus":
        strokes = []
        for petal in range(8):
            angle = petal * math.pi / 4
            strokes.append(_arc(0.16 * math.cos(angle), 0.16 * math.sin(angle), 0.28, angle - 0.8, 1.6, 16))
        strokes.append(_arc(0, 0, 0.08, 0, 6.2, 12))
        return strokes
    if key == "wave":
        strokes = []
        for band in range(5):
            base = -0.35 + band * 0.16
            stroke = []
            for index in range(40):
                x = -0.7 + 1.4 * index / 39
                y = base + 0.08 * math.sin(x * 7 + band)
                stroke.append((x, y))
            strokes.append(stroke)
        return strokes
    if key == "owl":
        return [
            _arc(0, 0.05, 0.4, 0, 6.28, 36),
            _arc(-0.14, 0.1, 0.1, 0, 6.2, 14),
            _arc(0.14, 0.1, 0.1, 0, 6.2, 14),
            _arc(-0.14, 0.1, 0.03, 0, 6.2, 8),
            _arc(0.14, 0.1, 0.03, 0, 6.2, 8),
            [(0, 0.02), (-0.05, -0.06), (0.05, -0.06), (0, 0.02)],
            _arc(0, -0.08, 0.22, 3.5, 2.3, 14),
        ]
    raise PatternRejected(f"unknown study {name}")


def study_polar(name: str) -> list[tuple[float, float]]:
    """A showcase contour engraving of one original study."""
    ink = _raster(study_strokes(name))
    return engraving_polar(contour_xy(ink, echoes=True))
