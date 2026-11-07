"""Oasis-style sand engravings: contours, spiral shading, or an echoed line.

The heavy work is a small grayscale grid. Pillow, which Home Assistant already
ships, reads the picture. No extra packages are required.
"""

from __future__ import annotations

import io
import math

from .patterns import MAX_POINTS, PatternRejected, densify

STYLE_CONTOURS = "contours"
STYLE_SPIRAL = "spiral"
STYLE_LINE = "line"
ART_STYLES = (STYLE_CONTOURS, STYLE_SPIRAL, STYLE_LINE)

# One corner bit per cell. Edge 0 bottom, 1 right, 2 top, 3 left.
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


def normalize_art_style(value: object) -> str:
    """Contours unless the saved option is one of the other two styles."""
    if isinstance(value, str) and value.strip().lower() in ART_STYLES:
        return value.strip().lower()
    return STYLE_CONTOURS


def grid_from_image(data: bytes, size: int = 72) -> list[list[float]]:
    """Darkness from 0 (paper) to 1 (ink), cropped to the disc."""
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


def _sample(grid: list[list[float]], x: float, y: float) -> float:
    size = len(grid)
    if size == 0 or math.hypot(x, y) > 1:
        return 0.0
    gx = (x + 1) / 2 * (size - 1)
    gy = (1 - y) / 2 * (size - 1)
    x0 = min(size - 1, max(0, int(gx)))
    y0 = min(size - 1, max(0, int(gy)))
    x1 = min(size - 1, x0 + 1)
    y1 = min(size - 1, y0 + 1)
    tx = gx - x0
    ty = gy - y0
    top = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx
    bottom = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx
    return top * (1 - ty) + bottom * ty


def _edge_xy(
    grid: list[list[float]], x: int, y: int, edge: int, level: float
) -> tuple[float, float]:
    size = len(grid)

    def lerp(v0: float, v1: float, p0: tuple[float, float], p1: tuple[float, float]) -> tuple[float, float]:
        if abs(v1 - v0) < 1e-9:
            t = 0.5
        else:
            t = min(1.0, max(0.0, (level - v0) / (v1 - v0)))
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

    def cell(cx: int, cy: int) -> tuple[float, float]:
        return ((cx / (size - 1)) * 2 - 1, 1 - (cy / (size - 1)) * 2)

    if edge == 0:
        return lerp(grid[y][x], grid[y][x + 1], cell(x, y), cell(x + 1, y))
    if edge == 1:
        return lerp(grid[y][x + 1], grid[y + 1][x + 1], cell(x + 1, y), cell(x + 1, y + 1))
    if edge == 2:
        return lerp(grid[y + 1][x], grid[y + 1][x + 1], cell(x, y + 1), cell(x + 1, y + 1))
    return lerp(grid[y][x], grid[y + 1][x], cell(x, y), cell(x, y + 1))


def _chains(segments: list[tuple[tuple[float, float], tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    def key(point: tuple[float, float]) -> tuple[float, float]:
        return (round(point[0], 3), round(point[1], 3))

    adjacency: dict[tuple[float, float], list[int]] = {}
    for index, (start, end) in enumerate(segments):
        adjacency.setdefault(key(start), []).append(index)
        adjacency.setdefault(key(end), []).append(index)
    used = [False] * len(segments)

    def walk(start_index: int, from_key: tuple[float, float]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        current = from_key
        previous = start_index
        while True:
            nxt = None
            for index in adjacency.get(current, []):
                if index != previous and not used[index]:
                    nxt = index
                    break
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
        chain = list(reversed(backward)) + [start, end, *forward]
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def contour_xy(grid: list[list[float]], levels: int = 22) -> list[tuple[float, float]]:
    """Nested iso-contours of a darkness grid, one polyline per level."""
    size = len(grid)
    if size < 2 or levels < 2:
        raise PatternRejected("The picture did not contain a shape")
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for step in range(1, levels + 1):
        level = step / (levels + 1)
        for y in range(size - 1):
            row = grid[y]
            nxt = grid[y + 1]
            for x in range(size - 1):
                index = (
                    (row[x] >= level)
                    + 2 * (row[x + 1] >= level)
                    + 4 * (nxt[x + 1] >= level)
                    + 8 * (nxt[x] >= level)
                )
                for left, right in _CASES[index]:
                    start = _edge_xy(grid, x, y, left, level)
                    end = _edge_xy(grid, x, y, right, level)
                    if math.hypot(*start) > 1.02 and math.hypot(*end) > 1.02:
                        continue
                    segments.append((start, end))
    chains = _chains(segments)
    if not chains:
        raise PatternRejected("The picture did not contain a shape")
    chains.sort(key=lambda chain: sum(math.hypot(x, y) for x, y in chain) / len(chain))
    return _join(chains)


def spiral_xy(grid: list[list[float]], turns: int = 46) -> list[tuple[float, float]]:
    """One spiral. Darkness nudges the radius by less than the gap to the next turn."""
    points: list[tuple[float, float]] = []
    steps = turns * 80
    pitch = 0.94 / turns
    for index in range(steps + 1):
        fraction = index / steps
        theta = turns * 2 * math.pi * fraction
        base = 0.02 + 0.94 * fraction
        dark = _sample(grid, base * math.cos(theta), base * math.sin(theta))
        rho = min(0.98, max(0.0, base + (dark - 0.5) * pitch * 0.85))
        points.append((rho * math.cos(theta), rho * math.sin(theta)))
    return points


def _offset(points: list[tuple[float, float]], distance: float) -> list[tuple[float, float]]:
    if len(points) < 2:
        return []
    shifted: list[tuple[float, float]] = []
    for index, (x, y) in enumerate(points):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        tx, ty = after[0] - before[0], after[1] - before[1]
        length = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / length, tx / length
        px, py = x + nx * distance, y + ny * distance
        if math.hypot(px, py) > 0.98:
            scale = 0.98 / math.hypot(px, py)
            px, py = px * scale, py * scale
        shifted.append((px, py))
    return shifted


def _wave_ring(radius: float, lobes: int) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    steps = max(48, lobes * 12)
    for index in range(steps + 1):
        theta = 2 * math.pi * index / steps
        rho = min(0.98, max(0.05, radius + 0.03 * math.sin(lobes * theta)))
        ring.append((rho * math.cos(theta), rho * math.sin(theta)))
    return ring


def echo_xy(points: list[tuple[float, float]], *, echoes: int = 4, waves: int = 5) -> list[tuple[float, float]]:
    """Parallel copies of a line drawing, plus a few flowing rings to fill the disc."""
    if len(points) < 2:
        raise PatternRejected("The drawing needs at least two points")
    cx = sum(x for x, _y in points) / len(points)
    cy = sum(y for _x, y in points) / len(points)
    chains = [list(points), _offset(points, 0.03), _offset(points, -0.03)]
    for scale in (0.82, 0.66, 0.5, 0.34)[: max(0, echoes - 1)]:
        chains.append([(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in points])
    for index in range(waves):
        chains.append(_wave_ring(0.28 + 0.14 * index, 7 + index * 2))
    return _join([chain for chain in chains if len(chain) >= 2])


def _join(chains: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    for chain in chains:
        if not chain:
            continue
        if not path:
            path.extend(chain)
            continue
        path = _bridge(path, chain)
    if len(path) < 2:
        raise PatternRejected("The engraving had no lines")
    return path


def _bridge(
    path: list[tuple[float, float]], chain: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    x0, y0 = path[-1]
    x1, y1 = chain[0]
    if math.hypot(x1 - x0, y1 - y0) <= 0.05:
        return [*path, *chain]
    theta0, rho0 = math.atan2(y0, x0), min(0.97, math.hypot(x0, y0))
    theta1, rho1 = math.atan2(y1, x1), min(0.97, math.hypot(x1, y1))
    while theta1 - theta0 > math.pi:
        theta1 -= 2 * math.pi
    while theta1 - theta0 < -math.pi:
        theta1 += 2 * math.pi
    ring = max(rho0, rho1, 0.08)
    bridge: list[tuple[float, float]] = []
    steps = max(2, int(abs(ring - rho0) / 0.03))
    for index in range(1, steps + 1):
        rho = rho0 + (ring - rho0) * index / steps
        bridge.append((rho * math.cos(theta0), rho * math.sin(theta0)))
    steps = max(2, int(abs(theta1 - theta0) / 0.08))
    for index in range(1, steps + 1):
        theta = theta0 + (theta1 - theta0) * index / steps
        bridge.append((ring * math.cos(theta), ring * math.sin(theta)))
    steps = max(2, int(abs(rho1 - ring) / 0.03))
    for index in range(1, steps + 1):
        rho = ring + (rho1 - ring) * index / steps
        bridge.append((rho * math.cos(theta1), rho * math.sin(theta1)))
    return [*path, *bridge, *chain]


def _length(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def _decimate(points: list[tuple[float, float]], spacing: float) -> list[tuple[float, float]]:
    if not points:
        return []
    kept = [points[0]]
    for point in points[1:]:
        if math.hypot(point[0] - kept[-1][0], point[1] - kept[-1][1]) >= spacing:
            kept.append(point)
    if kept[-1] != points[-1]:
        kept.append(points[-1])
    return kept


def engraving_thr(points: list[tuple[float, float]]) -> str:
    """One continuous centre-to-rim path, short enough to upload."""
    if len(points) < 2:
        raise PatternRejected("The engraving had no lines")
    spacing = 0.012
    simplified = points
    for _ in range(8):
        simplified = _decimate(points, spacing)
        if _length(simplified) <= 150 or spacing > 0.08:
            break
        spacing *= 1.35
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in simplified:
        rho = min(0.98, math.hypot(x, y))
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, rho))
    polar = [(polar[0][0], 0.0), *polar, (polar[-1][0], 1.0)]
    fitted = densify(polar, max_step=0.018)
    guard = 0
    while len(densify(fitted, max_step=0.01)) > min(MAX_POINTS - 1000, 20_000) and guard < 6:
        fitted = fitted[::2] or fitted
        fitted[0] = (fitted[0][0], 0.0)
        fitted[-1] = (fitted[-1][0], 1.0)
        fitted = densify(fitted, max_step=0.02)
        guard += 1
    fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    lines = [f"{theta:.6f} {min(1.0, max(0.0, rho)):.6f}" for theta, rho in fitted]
    return "\n".join(lines) + "\n"


def _box_blur(grid: list[list[float]], radius: int) -> list[list[float]]:
    size = len(grid)

    def pass_once(source: list[list[float]], horizontal: bool) -> list[list[float]]:
        output = [[0.0] * size for _ in range(size)]
        for y in range(size):
            for x in range(size):
                total = 0.0
                count = 0
                for offset in range(-radius, radius + 1):
                    xx = x + offset if horizontal else x
                    yy = y if horizontal else y + offset
                    if 0 <= xx < size and 0 <= yy < size:
                        total += source[yy][xx]
                        count += 1
                output[y][x] = total / max(1, count)
        return output

    return pass_once(pass_once(grid, True), False)


def _relief(grid: list[list[float]]) -> list[list[float]]:
    """Spread a hard shape into a height field so many contour lines can form."""
    blurred = _box_blur(_box_blur(grid, 5), 3)
    size = len(blurred)
    field: list[list[float]] = []
    for y in range(size):
        row: list[float] = []
        for x in range(size):
            nx = (x / (size - 1)) * 2 - 1
            ny = 1 - (y / (size - 1)) * 2
            rho = min(1.0, math.hypot(nx, ny))
            theta = math.atan2(ny, nx)
            if rho >= 1:
                row.append(0.0)
                continue
            wave = 0.045 * math.sin(6 * theta + 3 * rho)
            height = blurred[y][x] * 0.78 + (1 - rho) * 0.28 + wave
            row.append(min(1.0, max(0.0, height)))
        field.append(row)
    return field


def art_from_image(data: bytes, style: str) -> str:
    """Contours or spiral shading from a generated picture."""
    grid = _relief(grid_from_image(data))
    chosen = normalize_art_style(style)
    if chosen == STYLE_SPIRAL:
        drawn = spiral_xy(grid)
    elif chosen == STYLE_LINE:
        drawn = echo_xy(contour_xy(grid, levels=3), echoes=2, waves=2)
    else:
        drawn = contour_xy(grid, levels=26)
    return engraving_thr(drawn)


def art_from_points(points: list[tuple[float, float]], style: str) -> str:
    """Text-model fallback: echo the line and fill the disc with waves."""
    chosen = normalize_art_style(style)
    if chosen == STYLE_LINE:
        return engraving_thr(echo_xy(points, echoes=2, waves=3))
    return engraving_thr(echo_xy(points, echoes=4, waves=5))
