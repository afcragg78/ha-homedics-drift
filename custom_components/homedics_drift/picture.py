"""Picture to sand: detailed line art, then echoes that hug it and relax into circles.

The subject is drawn as vectors. Echoes come from a high-resolution distance
field of that silhouette, smoothed so they are not stair-steps, and blended
toward a circle only as they approach the rim. Joins stay on those echoes.
"""

from __future__ import annotations

import io
import math

from .patterns import MAX_POINTS, PatternRejected, densify, parse_thr

STYLE_CONTOURS = "contours"
STYLE_LINE = "line"
ART_STYLES = (STYLE_CONTOURS, STYLE_LINE)
_GRID = 1024
_BALL = 0.017


def normalize_art_style(value: object) -> str:
    """Contours unless the caller asked for a plain line drawing."""
    if isinstance(value, str) and value.strip().lower() in ("line", "line drawing", "lines"):
        return STYLE_LINE
    return STYLE_CONTOURS


def _chaikin(points: list[tuple[float, float]], passes: int = 2) -> list[tuple[float, float]]:
    current = points
    for _ in range(passes):
        if len(current) < 3:
            break
        nxt = [current[0]]
        for left, right in zip(current, current[1:], strict=False):
            nxt.append((0.75 * left[0] + 0.25 * right[0], 0.75 * left[1] + 0.25 * right[1]))
            nxt.append((0.25 * left[0] + 0.75 * right[0], 0.25 * left[1] + 0.75 * right[1]))
        nxt.append(current[-1])
        current = nxt
    return current


def _arc(cx: float, cy: float, radius: float, start: float, sweep: float, steps: int = 28) -> list[tuple[float, float]]:
    return [
        (
            cx + radius * math.cos(start + sweep * index / steps),
            cy + radius * math.sin(start + sweep * index / steps),
        )
        for index in range(steps + 1)
    ]


def _ellipse(cx: float, cy: float, rx: float, ry: float, steps: int = 72) -> list[tuple[float, float]]:
    return [
        (cx + rx * math.cos(2 * math.pi * index / steps), cy + ry * math.sin(2 * math.pi * index / steps))
        for index in range(steps + 1)
    ]


def _out_and_back(stroke: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Travel a whisker or stripe and return on the same line."""
    smooth = _chaikin(stroke, 1)
    return [*smooth, *reversed(smooth[:-1])]


def _catmull(points: list[tuple[float, float]], samples: int = 8) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points
    padded = [points[0], *points, points[-1]]
    out: list[tuple[float, float]] = []
    for index in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[index - 1 : index + 3]
        for step in range(samples):
            t = step / samples
            t2 = t * t
            t3 = t2 * t
            def coord(i: int) -> float:
                return 0.5 * (
                    (2 * p1[i])
                    + (-p0[i] + p2[i]) * t
                    + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2
                    + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t3
                )
            out.append((coord(0), coord(1)))
    out.append(points[-1])
    return out


def study_strokes(name: str) -> tuple[list[list[tuple[float, float]]], list[tuple[float, float]]]:
    """Interior drawing plus the outer silhouette. Original geometry, not a copied character."""
    key = name.lower()
    if key == "tiger":
        head = _ellipse(0.0, 0.02, 0.40, 0.34, 90)
        strokes = [
            [(0.0, 0.0), (0.0, -0.06), (-0.045, -0.11), (0.045, -0.11), (0.0, -0.06)],
            [(0.0, -0.06), (-0.09, -0.16), (0.0, -0.2), (0.09, -0.16), (0.0, -0.06)],
            _out_and_back([(-0.05, -0.08), (-0.42, -0.02)]),
            _out_and_back([(-0.05, -0.1), (-0.46, -0.1)]),
            _out_and_back([(-0.04, -0.12), (-0.4, -0.18)]),
            _out_and_back([(0.05, -0.08), (0.42, -0.02)]),
            _out_and_back([(0.05, -0.1), (0.46, -0.1)]),
            _out_and_back([(0.04, -0.12), (0.4, -0.18)]),
            _arc(-0.15, 0.08, 0.075, 0, 6.283, 24),
            _arc(-0.15, 0.08, 0.028, 0, 6.283, 12),
            _arc(0.15, 0.08, 0.075, 0, 6.283, 24),
            _arc(0.15, 0.08, 0.028, 0, 6.283, 12),
            _out_and_back([(0.0, 0.16), (-0.06, 0.28), (0.0, 0.34)]),
            _out_and_back([(0.0, 0.16), (0.07, 0.28), (0.02, 0.36)]),
            _out_and_back([(-0.1, 0.14), (-0.16, 0.26), (-0.08, 0.3)]),
            _out_and_back([(0.1, 0.14), (0.16, 0.26), (0.08, 0.3)]),
            _arc(-0.24, 0.36, 0.12, 0.2, 2.6, 16),
            _arc(0.24, 0.36, 0.12, math.pi - 2.8, 2.6, 16),
            _out_and_back([(-0.22, 0.02), (-0.32, -0.08), (-0.24, -0.16)]),
            _out_and_back([(0.22, 0.02), (0.32, -0.08), (0.24, -0.16)]),
            head,
        ]
        return strokes, head
    if key == "koi":
        body = _catmull(
            [(0.0, 0.0), (-0.28, 0.12), (-0.42, 0.0), (-0.22, -0.14), (0.2, -0.1), (0.36, 0.0), (0.12, 0.12), (0.0, 0.0)],
            6,
        )
        scales = []
        for row in range(4):
            for col in range(5):
                cx = -0.22 + col * 0.1
                cy = 0.08 - row * 0.055
                if (cx + 0.05) ** 2 / 0.28 + cy ** 2 / 0.12 < 1:
                    scales.append(_arc(cx, cy, 0.035, 0.2, 2.6, 8))
        strokes = [
            body,
            [(0.28, 0.04), (0.55, 0.22), (0.4, 0.0), (0.55, -0.22), (0.28, -0.04)],
            _out_and_back([(0.05, 0.1), (0.0, 0.28), (-0.12, 0.16)]),
            _out_and_back([(-0.05, -0.08), (-0.16, -0.26), (0.02, -0.12)]),
            _arc(0.12, 0.04, 0.035, 0, 6.2, 12),
            _arc(0.12, 0.04, 0.012, 0, 6.2, 8),
            [(0.0, 0.06), (0.08, 0.02), (0.0, -0.02)],
            *scales,
        ]
        return strokes, body
    if key == "lotus":
        petals = []
        for index in range(12):
            angle = index * math.pi / 6
            petals.append(
                _catmull(
                    [
                        (0.05 * math.cos(angle), 0.05 * math.sin(angle)),
                        (0.28 * math.cos(angle + 0.18), 0.28 * math.sin(angle + 0.18)),
                        (0.46 * math.cos(angle), 0.46 * math.sin(angle)),
                        (0.28 * math.cos(angle - 0.18), 0.28 * math.sin(angle - 0.18)),
                        (0.05 * math.cos(angle), 0.05 * math.sin(angle)),
                    ],
                    4,
                )
            )
            petals.append(
                _out_and_back(
                    [
                        (0.08 * math.cos(angle), 0.08 * math.sin(angle)),
                        (0.4 * math.cos(angle), 0.4 * math.sin(angle)),
                    ]
                )
            )
        heart = [(0.0, 0.0), *_ellipse(0, 0, 0.08, 0.08, 24)]
        return [heart, *petals], _ellipse(0, 0, 0.5, 0.5, 80)
    if key == "wave":
        strokes = [[(0.0, 0.0), (0.0, 0.02)]]
        for band in range(6):
            base = -0.22 + band * 0.09
            crest = []
            for index in range(48):
                x = -0.62 + 1.24 * index / 47
                y = base + 0.07 * math.sin(x * 6.5 + band * 0.7) + 0.03 * math.sin(x * 13)
                crest.append((x, y))
            strokes.append(_chaikin(crest, 1))
            strokes.append(_out_and_back([(crest[12][0], crest[12][1]), (crest[12][0], crest[12][1] + 0.05)]))
        return strokes, _ellipse(0, 0, 0.7, 0.42, 80)
    if key == "owl":
        head = _ellipse(0, 0.08, 0.36, 0.34, 80)
        feathers = []
        for row in range(4):
            y = -0.05 - row * 0.07
            for col in range(5):
                x = -0.2 + col * 0.1
                feathers.append(_arc(x, y, 0.045, 0.15, 2.8, 8))
        strokes = [
            [(0.0, 0.0), (0.0, 0.02), (-0.035, -0.02), (0.035, -0.02), (0.0, 0.02)],
            head,
            _arc(-0.22, 0.4, 0.1, 0.6, 2.2, 12),
            _arc(0.22, 0.4, 0.1, math.pi - 2.8, 2.2, 12),
            _arc(-0.13, 0.12, 0.1, 0, 6.28, 28),
            _arc(-0.13, 0.12, 0.045, 0, 6.28, 16),
            _arc(0.13, 0.12, 0.1, 0, 6.28, 28),
            _arc(0.13, 0.12, 0.045, 0, 6.28, 16),
            [(0.0, 0.04), (-0.04, -0.04), (0.04, -0.04), (0.0, 0.04)],
            *feathers,
            _arc(-0.05, -0.28, 0.22, 0.4, 2.2, 14),
            _arc(0.05, -0.28, 0.22, math.pi - 2.6, 2.2, 14),
        ]
        return strokes, head
    raise PatternRejected(f"unknown study {name}")


def _mask(polygons: list[list[tuple[float, float]]], size: int) -> list[list[bool]]:
    from PIL import Image, ImageDraw

    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)

    def pix(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [((x + 1) * 0.5 * (size - 1), (1 - y) * 0.5 * (size - 1)) for x, y in points]

    for polygon in polygons:
        if len(polygon) >= 3:
            draw.polygon(pix(polygon), fill=255)
    ink = image.load()
    return [[ink[x, y] > 0 for x in range(size)] for y in range(size)]


def _silhouette(mask: list[list[bool]], samples: int = 360) -> list[float]:
    size = len(mask)
    rhos = [0.0] * samples
    for index in range(samples):
        theta = -math.pi + 2 * math.pi * index / samples
        best = 0.0
        for step in range(size // 2):
            rho = step / (size / 2)
            x = int(round((rho * math.cos(theta) + 1) * 0.5 * (size - 1)))
            y = int(round((1 - rho * math.sin(theta)) * 0.5 * (size - 1)))
            if 0 <= x < size and 0 <= y < size and mask[y][x]:
                best = rho
        rhos[index] = best
    smooth = rhos[:]
    for _ in range(2):
        smooth = [
            0.25 * smooth[(i - 1) % samples] + 0.5 * smooth[i] + 0.25 * smooth[(i + 1) % samples]
            for i in range(samples)
        ]
    return smooth


def _echo_spiral(shape: list[float]) -> list[tuple[float, float]]:
    """One spiral. Near the subject it copies the outline; toward the rim it becomes round."""
    samples = len(shape)
    peak = max(shape) if shape else 0.2
    spacing = _BALL
    turns = max(8, int((0.96 - peak) / spacing) + 4)
    path: list[tuple[float, float]] = []
    per = 220
    for turn in range(turns):
        offset = 0.012 + turn * spacing
        for step in range(per):
            theta = -math.pi + 2 * math.pi * (turn + step / per)
            bucket = int((theta + math.pi) / (2 * math.pi) * samples) % samples
            hugged = shape[bucket] + offset
            circle = min(0.97, 0.08 + offset * 1.35)
            relax = min(1.0, max(0.0, offset / 0.7)) ** 1.6
            rho = (1 - relax) * hugged + relax * max(circle, shape[bucket] + offset)
            rho = min(0.975, max(shape[bucket] + 0.014, rho))
            path.append((rho * math.cos(theta), rho * math.sin(theta)))
    return path


def _along(loop: list[tuple[float, float]], start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    """Walk the shorter way around a closed outline. The join sits on that outline."""
    if len(loop) < 4:
        return [end]

    def nearest(point: tuple[float, float]) -> int:
        return min(range(len(loop)), key=lambda index: math.hypot(loop[index][0] - point[0], loop[index][1] - point[1]))

    i0, i1 = nearest(start), nearest(end)
    forward = []
    index = i0
    while index != i1:
        forward.append(loop[index])
        index = (index + 1) % len(loop)
    backward = []
    index = i0
    while index != i1:
        backward.append(loop[index])
        index = (index - 1) % len(loop)
    chosen = forward if len(forward) <= len(backward) else backward
    return [*chosen, loop[i1], end]


def _join_short(
    strokes: list[list[tuple[float, float]]],
    silhouette: list[tuple[float, float]] | None = None,
) -> list[tuple[float, float]]:
    path = list(strokes[0])
    for stroke in strokes[1:]:
        if not stroke:
            continue
        gap = math.hypot(stroke[0][0] - path[-1][0], stroke[0][1] - path[-1][1])
        if gap <= 0.08:
            path.extend(stroke)
            continue
        if silhouette:
            path.extend(_along(silhouette, path[-1], stroke[0]))
        path.extend(stroke)
    return path


def _to_polar(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 2:
        raise PatternRejected("That picture did not contain a shape")
    polar: list[tuple[float, float]] = []
    previous = 0.0
    last_xy = points[0]
    for x, y in points:
        if math.hypot(x - last_xy[0], y - last_xy[1]) < 0.004 and polar:
            continue
        last_xy = (x, y)
        rho = min(0.985, max(0.0, math.hypot(x, y)))
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, rho))
    if 0 < polar[0][1] <= 0.04:
        polar.insert(0, (polar[0][0], 0.0))
    polar.append((polar[-1][0], 1.0))
    step = 0.012
    fitted = densify(polar, max_step=step)
    while len(fitted) > 18_000 and step < 0.04:
        step *= 1.2
        fitted = densify(polar, max_step=step)
    while len(fitted) < 900 and step > 0.005:
        step *= 0.8
        fitted = densify(polar, max_step=step)
    if len(fitted) > MAX_POINTS:
        stride = math.ceil(len(fitted) / 14_000)
        fitted = densify(fitted[::stride], max_step=0.016)
    if fitted[0][1] < 0.05:
        fitted[0] = (fitted[0][0], 0.0)
    fitted[-1] = (fitted[-1][0], 1.0)
    return densify(fitted, max_step=0.012)


def engrave(strokes: list[list[tuple[float, float]]], silhouette: list[tuple[float, float]], *, echoes: bool) -> list[tuple[float, float]]:
    """Detail strokes, then one hugging spiral when echoes are on."""
    drawn = [stroke for stroke in strokes if len(stroke) >= 2]
    if not drawn:
        raise PatternRejected("That picture did not contain a shape")
    path = _join_short_safe(drawn, silhouette)
    if echoes and len(silhouette) >= 8:
        mask = _mask([silhouette], _GRID)
        if any(cell for row in mask for cell in row):
            spiral = _echo_spiral(_silhouette(mask))
            if spiral:
                path = _attach_spiral(path, spiral)
    return _to_polar(path)


def _join_short_safe(
    strokes: list[list[tuple[float, float]]],
    silhouette: list[tuple[float, float]] | None = None,
) -> list[tuple[float, float]]:
    return _join_short(strokes, silhouette)


def _attach_spiral(path: list[tuple[float, float]], spiral: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Leave the drawing on the nearest echo sample. The hop is one ball-width."""
    end = path[-1]
    nearest = min(range(len(spiral)), key=lambda index: math.hypot(spiral[index][0] - end[0], spiral[index][1] - end[1]))
    ordered = spiral[nearest:] + spiral[:nearest]
    return [*path, *ordered]


def study_polar(name: str) -> list[tuple[float, float]]:
    strokes, silhouette = study_strokes(name)
    return engrave(strokes, silhouette, echoes=True)


def grid_from_image(data: bytes, size: int = 384) -> list[list[float]]:
    """Darkness 0..1. Outside the disc is paper."""
    from PIL import Image, ImageFilter

    image = Image.open(io.BytesIO(data)).convert("L")
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.GaussianBlur(radius=max(1, size // 180)))
    samples = list(image.tobytes())
    low, high = min(samples), max(samples)
    span = max(1, high - low)
    grid: list[list[float]] = []
    for y in range(size):
        row = []
        for x in range(size):
            shade = 1.0 - (samples[y * size + x] - low) / span
            nx = (x / (size - 1)) * 2 - 1
            ny = 1 - (y / (size - 1)) * 2
            if math.hypot(nx, ny) > 1:
                shade = 0.0
            row.append(shade)
        grid.append(row)
    return grid


def _largest_blob(mask: list[list[bool]]) -> list[list[bool]]:
    size = len(mask)
    seen = [[False] * size for _ in range(size)]
    best: list[tuple[int, int]] = []
    for y in range(size):
        for x in range(size):
            if not mask[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            cells: list[tuple[int, int]] = []
            while stack:
                cx, cy = stack.pop()
                cells.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < size and 0 <= ny < size and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(cells) > len(best):
                best = cells
    out = [[False] * size for _ in range(size)]
    for x, y in best:
        out[y][x] = True
    return out


def _fill_holes(mask: list[list[bool]]) -> list[list[bool]]:
    """Anything not reachable from the border through paper is part of the subject."""
    size = len(mask)
    seen = [[False] * size for _ in range(size)]
    stack = [(x, 0) for x in range(size)] + [(x, size - 1) for x in range(size)]
    stack += [(0, y) for y in range(size)] + [(size - 1, y) for y in range(size)]
    while stack:
        x, y = stack.pop()
        if not (0 <= x < size and 0 <= y < size) or seen[y][x] or mask[y][x]:
            continue
        seen[y][x] = True
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return [[mask[y][x] or not seen[y][x] for x in range(size)] for y in range(size)]


def _photo_parts(grid: list[list[float]]) -> tuple[list[list[tuple[float, float]]], list[tuple[float, float]]]:
    """The largest dark subject, centred, with its outline as the drawing."""
    size = len(grid)
    raw = [
        [
            grid[y][x] > 0.42 and math.hypot((x / (size - 1)) * 2 - 1, 1 - (y / (size - 1)) * 2) < 0.98
            for x in range(size)
        ]
        for y in range(size)
    ]
    mask = _fill_holes(_largest_blob(raw))
    shape = _silhouette(mask, samples=360)
    if max(shape) < 0.05:
        raise PatternRejected("That picture did not contain a shape")
    peak = max(shape)
    # Angles that miss the subject must not dive to the centre. Hold the
    # outer radius across those gaps so the outline stays on the animal.
    closed = []
    for rho in shape:
        closed.append(rho if rho >= peak * 0.45 else None)
    for index, rho in enumerate(closed):
        if rho is not None:
            continue
        left = next(closed[(index - step) % len(closed)] for step in range(1, len(closed)) if closed[(index - step) % len(closed)] is not None)
        right = next(closed[(index + step) % len(closed)] for step in range(1, len(closed)) if closed[(index + step) % len(closed)] is not None)
        closed[index] = (left + right) / 2
    shape = [float(rho) for rho in closed]
    scale = 0.58 / peak
    silhouette = []
    for index, rho in enumerate(shape):
        theta = -math.pi + 2 * math.pi * index / len(shape)
        silhouette.append((scale * rho * math.cos(theta), scale * rho * math.sin(theta)))
    # A centre point only if the subject covers the origin; otherwise the
    # outline itself is the start and we do not cut across the animal.
    strokes = [silhouette + [silhouette[0]]]
    return strokes, silhouette


def art_from_image(data: bytes, style: object) -> str:
    """Contours or a line from a photo."""
    strokes, silhouette = _photo_parts(grid_from_image(data))
    if sum(math.hypot(x, y) for x, y in silhouette) < 1:
        raise PatternRejected("That picture did not contain a shape")
    polar = engrave(strokes, silhouette, echoes=normalize_art_style(style) == STYLE_CONTOURS)
    return "".join(f"{theta:.6f} {rho:.6f}\n" for theta, rho in polar)


def art_from_points(points: list[tuple[float, float]], style: object) -> str:
    """Wrap a model's line in echo contours, or keep the line."""
    if len(points) < 2:
        raise PatternRejected("The drawing needs at least two points")
    polar = engrave([points], points, echoes=normalize_art_style(style) == STYLE_CONTOURS)
    return "".join(f"{theta:.6f} {rho:.6f}\n" for theta, rho in polar)


def xy_from_thr(text: str) -> list[tuple[float, float]]:
    return [(rho * math.cos(theta), rho * math.sin(theta)) for theta, rho in parse_thr(text)]
