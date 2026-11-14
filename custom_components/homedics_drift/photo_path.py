"""Turn a photo into one continuous sand path, then check it on the twin.

The picture is the style of Drifted's weather design: the subject is swept
smooth, its outline is drawn twice, and background rows flow around it instead
of through it. The ball never lifts. Nothing here imports Home Assistant.
Pillow reads the photo. Numpy is the same grid the twin uses.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from .patterns import MAX_POINTS, PatternRejected, densify
from .twin import Sand, render_png

STEP = 0.014
RIM = 0.96
OUTLINE_INSET = 0.034
WORK = 160

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

_PRESETS: tuple[dict[str, float], ...] = (
    {"spacing": 0.070, "scale": 0.68, "angle": 0.0, "wave": 0.012, "threshold": 0.48, "sweep": 0.045},
    {"spacing": 0.085, "scale": 0.74, "angle": 18.0, "wave": 0.0, "threshold": 0.40, "sweep": 0.050},
    {"spacing": 0.055, "scale": 0.62, "angle": -14.0, "wave": 0.016, "threshold": 0.56, "sweep": 0.040},
)


@dataclass
class PhotoDrawing:
    """The path that won, and the twin picture of it."""

    thr: str
    png: bytes
    score: float
    recognizable: float
    coverage: float
    stray: float
    points: int
    spacing: float
    scale: float


def check_rotation(value: object) -> float:
    """Degrees counter-clockwise, from -180 to 180. Zero leaves the photo as it is."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise PatternRejected("rotate must be a number") from err
    if not math.isfinite(number) or not -180.0 <= number <= 180.0:
        raise PatternRejected("rotate must be between -180 and 180")
    return number


def configured_camera(options: dict[str, object] | None) -> str | None:
    """The feedback camera, or None when the option is missing or blank.

    The hook is off unless a camera entity id is saved.
    """
    if not options:
        return None
    value = options.get("photo_feedback_camera", "")
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def resolve_photo_file(config_dir, raw: str):
    """A photo under ``/config/www`` or ``/config/media``.

    ``/local/...`` is the www folder. Anything else, including ``..`` that
    leaves those folders, is refused. Media-source ids are not files.
    """
    from pathlib import Path

    text = raw.strip()
    if not text:
        raise PatternRejected("Name a photo")
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "file://")):
        raise PatternRejected("The photo has to be a file in /config/www or /config/media")
    if lowered.startswith("media-source:"):
        raise PatternRejected("Use a media-source id, not a file path")
    root = Path(config_dir).expanduser().resolve()
    if text.startswith("/local/"):
        text = str(root / "www" / text[len("/local/") :].lstrip("/"))
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / "www" / path
    path = path.resolve()
    www = (root / "www").resolve()
    media = (root / "media").resolve()
    if not (path.is_relative_to(www) or path.is_relative_to(media)):
        raise PatternRejected("The photo has to stay in /config/www or /config/media")
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise PatternRejected("The photo must be a png, jpg, webp, gif, or bmp")
    return path


def photo_to_sand(
    data: bytes,
    *,
    rotate: float = 0.0,
    detail: str = "preview",
) -> PhotoDrawing:
    """Build a few pictures, score each on the twin, and keep the best.

    ``detail="fast"`` is one coarse pass for tests. ``preview`` is what the
    service runs before anything is sent to the table.
    """
    grey = _open_grey(data)
    fast = detail == "fast"
    presets = _PRESETS[:1] if fast else _PRESETS
    score_n = 72 if fast else 120
    final_n = 96 if fast else 200
    best: PhotoDrawing | None = None
    best_xy: list[tuple[float, float]] | None = None
    failures: list[str] = []
    for preset in presets:
        try:
            xy, outline, stray = build_xy(grey, preset)
        except PatternRejected as err:
            failures.append(err.message)
            continue
        xy = rotate_xy(xy, rotate)
        outline = rotate_xy(outline, rotate)
        png, sand = render_png(xy, n=score_n, size=160, seed=1)
        recognizable, coverage = _score_sand(sand, outline)
        score = _composite(recognizable, coverage, stray)
        if best is None or score > best.score:
            best = PhotoDrawing(
                thr="",
                png=png,
                score=score,
                recognizable=recognizable,
                coverage=coverage,
                stray=stray,
                points=len(xy),
                spacing=preset["spacing"],
                scale=preset["scale"],
            )
            best_xy = xy
    if best is None or best_xy is None:
        detail_text = failures[0] if failures else "that photo has no clear subject"
        raise PatternRejected(
            "Could not find a subject in that photo. "
            "Use a bold shape on a plain background. "
            f"({detail_text})"
        )
    png, _sand = render_png(best_xy, n=final_n, size=480, seed=1)
    thr = xy_to_thr(best_xy)
    return PhotoDrawing(
        thr=thr,
        png=png,
        score=best.score,
        recognizable=best.recognizable,
        coverage=best.coverage,
        stray=best.stray,
        points=len(parse_xy_count(thr)),
        spacing=best.spacing,
        scale=best.scale,
    )


def parse_xy_count(thr: str) -> list[tuple[float, float]]:
    """Polar points already in the ``.thr`` text. Used by the point cap."""
    from .patterns import parse_thr

    return parse_thr(thr)


def build_xy(
    grey: np.ndarray, preset: dict[str, float]
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], float]:
    """One continuous path, the subject outline, and the longest stray link."""
    mask = _subject_mask(grey, preset["threshold"])
    contour = _trace(mask)
    outline = _outline_xy(contour, preset["scale"])
    radius_at = _radius_table(outline)
    path, stray = _compose(radius_at, preset)
    path = _clamp_disc(path)
    return path, outline, stray


def rotate_xy(points: list[tuple[float, float]], degrees: float) -> list[tuple[float, float]]:
    """Turn the picture counter-clockwise. Zero leaves it as drawn."""
    if not degrees:
        return points
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return [(x * cosine - y * sine, x * sine + y * cosine) for x, y in points]


def xy_to_thr(points: list[tuple[float, float]]) -> str:
    """Theta-rho text. Theta is unwrapped so a loop does not jump the long way.

    The track is coarsened until ``patterns.thr_to_wire`` can store it.
    """
    if len(points) < 2:
        raise PatternRejected("The photo did not become a path")
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        radius = min(1.0, math.hypot(x, y))
        theta = math.atan2(y, x) if radius > 1e-8 else previous
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, radius))
    step = 0.012
    thinned = polar
    dense = densify(thinned, max_step=step)
    while len(dense) > MAX_POINTS - 1000 and step < 0.06:
        step *= 1.25
        thinned = _thin(polar, step)
        dense = densify(thinned, max_step=step)
    if len(dense) > MAX_POINTS:
        raise PatternRejected(f"the pattern has {len(dense)} points; the limit is {MAX_POINTS}")
    lines = [f"{theta:.6f} {min(1.0, max(0.0, rho)):.6f}" for theta, rho in dense]
    return "\n".join(lines) + "\n"


def match_score(left: bytes, right: bytes) -> float:
    """How much of the fine light and dark in two pictures agrees, from 0 to 1.

    This is the same idea as Drifted's webcam comparison: line the two discs
    up, take out the slow lighting, and correlate what is left. 1 is a copy.
    """
    a = _disc_highpass(left)
    b = _disc_highpass(right)
    mask = a[2]
    av, bv = a[0][mask], b[0][mask]
    av = av - av.mean()
    bv = bv - bv.mean()
    denom = math.sqrt(float((av * av).sum() * (bv * bv).sum()) + 1e-12)
    corr = float((av * bv).sum() / denom)
    return max(0.0, min(1.0, corr))


def _disc_highpass(data: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    image = Image.open(io.BytesIO(data)).convert("L").resize((96, 96), Image.Resampling.BILINEAR)
    values = np.asarray(image, dtype=np.float64)
    blur = np.asarray(image.filter(ImageFilter.BoxBlur(4)), dtype=np.float64)
    high = values - blur
    yy, xx = np.mgrid[0:96, 0:96]
    mask = (xx - 47.5) ** 2 + (yy - 47.5) ** 2 <= 44**2
    return high, values, mask


def _open_grey(data: bytes) -> np.ndarray:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as err:
        raise PatternRejected("That file is not a picture this integration can read") from err
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)
    image = image.convert("L")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((WORK, WORK), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.BoxBlur(1))
    return np.asarray(image, dtype=np.float64) / 255.0


def _subject_mask(grey: np.ndarray, threshold: float) -> np.ndarray:
    """The bold blob of the subject, inside the round table."""
    gy, gx = np.gradient(grey)
    edges = np.hypot(gx, gy)
    border = np.concatenate((grey[0, :], grey[-1, :], grey[:, 0], grey[:, -1]))
    level = float(np.median(border))
    salience = np.abs(grey - level)
    circle = _circle()
    combined = 0.55 * _stretch(edges, circle) + 0.45 * _stretch(salience, circle)
    cutoff = 0.22 + 0.5 * threshold
    binary = (combined >= cutoff) & circle
    binary = _close(binary)
    binary = _fill_holes(binary) & circle
    chosen = _pick_component(binary, circle)
    area = int(chosen.sum())
    disc = int(circle.sum())
    if area < 0.02 * disc or area > 0.88 * disc:
        raise PatternRejected("the subject did not stand out from the background")
    return chosen


def _circle() -> np.ndarray:
    yy, xx = np.mgrid[0:WORK, 0:WORK]
    center = (WORK - 1) / 2
    return (xx - center) ** 2 + (yy - center) ** 2 <= (WORK * 0.48) ** 2


def _stretch(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    sample = values[mask]
    low, high = np.percentile(sample, [5, 95])
    return np.clip((values - low) / (float(high - low) + 1e-6), 0, 1)


def _close(mask: np.ndarray) -> np.ndarray:
    image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    image = image.filter(ImageFilter.MaxFilter(5))
    image = image.filter(ImageFilter.MinFilter(3))
    return np.asarray(image) > 0


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """True for the subject and for any hole that does not touch the border."""
    height, width = mask.shape
    outside = np.zeros((height, width), dtype=bool)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        if not mask[0, x]:
            stack.append((0, x))
        if not mask[height - 1, x]:
            stack.append((height - 1, x))
    for y in range(height):
        if not mask[y, 0]:
            stack.append((y, 0))
        if not mask[y, width - 1]:
            stack.append((y, width - 1))
    while stack:
        y, x = stack.pop()
        if y < 0 or x < 0 or y >= height or x >= width or outside[y, x] or mask[y, x]:
            continue
        outside[y, x] = True
        stack.extend(((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))
    return mask | ~outside


def _pick_component(mask: np.ndarray, circle: np.ndarray) -> np.ndarray:
    labels, count = _label(mask & circle)
    if count == 0:
        raise PatternRejected("the subject did not stand out from the background")
    center = WORK // 2
    if labels[center, center]:
        return labels == labels[center, center]
    best_id = 0
    best_score = -1.0
    for index in range(1, count + 1):
        ys, xs = np.where(labels == index)
        if len(xs) < 8:
            continue
        cy = float(ys.mean())
        cx = float(xs.mean())
        near = 1.0 - min(1.0, math.hypot(cx - center, cy - center) / (WORK * 0.45))
        score = len(xs) * (0.35 + near)
        if score > best_score:
            best_score = score
            best_id = index
    if best_id == 0:
        raise PatternRejected("the subject did not stand out from the background")
    return labels == best_id


def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    current = 0
    ys, xs = np.where(mask)
    for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
        if labels[y, x]:
            continue
        current += 1
        stack = [(y, x)]
        labels[y, x] = current
        while stack:
            cy, cx = stack.pop()
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and labels[ny, nx] == 0:
                    labels[ny, nx] = current
                    stack.append((ny, nx))
    return labels, current


_NEIGHBORS = ((-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))


def _trace(mask: np.ndarray) -> list[tuple[int, int]]:
    """Moore neighborhood around the blob. Points are (x, y), y down."""
    height, width = mask.shape
    start: tuple[int, int] | None = None
    for y in range(height):
        row = mask[y]
        for x in range(width):
            if row[x] and (x == 0 or not row[x - 1]):
                start = (x, y)
                break
        if start is not None:
            break
    if start is None:
        raise PatternRejected("the subject did not stand out from the background")
    contour = [start]
    x, y = start
    direction = 0
    for _ in range(width * height * 2):
        found = False
        for turn in range(8):
            nd = (direction + turn) % 8
            nx = x + _NEIGHBORS[nd][0]
            ny = y + _NEIGHBORS[nd][1]
            if 0 <= nx < width and 0 <= ny < height and mask[ny, nx]:
                x, y = nx, ny
                direction = (nd + 5) % 8
                found = True
                break
        if not found or (x, y) == start:
            break
        contour.append((x, y))
    if len(contour) < 12:
        raise PatternRejected("the subject outline was too small to draw")
    return _simplify(contour, 1.6)


def _simplify(points: list[tuple[int, int]], epsilon: float) -> list[tuple[int, int]]:
    """Douglas-Peucker on a closed contour."""
    if len(points) < 8:
        return points
    open_points = points + [points[0]]
    kept = _douglas(open_points, epsilon)
    if kept and kept[0] == kept[-1]:
        kept = kept[:-1]
    if len(kept) < 8:
        return points[:: max(1, len(points) // 48)]
    return _smooth_closed([(float(x), float(y)) for x, y in kept])


def _douglas(points: list[tuple[int, int]], epsilon: float) -> list[tuple[int, int]]:
    if len(points) < 3:
        return points
    ax, ay = points[0]
    bx, by = points[-1]
    span = math.hypot(bx - ax, by - ay) or 1.0
    worst = 0.0
    index = 0
    for position, (x, y) in enumerate(points[1:-1], start=1):
        distance = abs((by - ay) * x - (bx - ax) * y + bx * ay - by * ax) / span
        if distance > worst:
            worst = distance
            index = position
    if worst <= epsilon:
        return [points[0], points[-1]]
    left = _douglas(points[: index + 1], epsilon)
    right = _douglas(points[index:], epsilon)
    return left[:-1] + right


def _smooth_closed(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    current = points
    for _ in range(2):
        nxt: list[tuple[float, float]] = []
        count = len(current)
        for index, point in enumerate(current):
            prev = current[(index - 1) % count]
            nxt.append(((prev[0] + point[0]) / 2, (prev[1] + point[1]) / 2))
            nxt.append(((prev[0] + 2 * point[0]) / 3, (prev[1] + 2 * point[1]) / 3))
        current = nxt
    simplified = _douglas([(int(x), int(y)) for x, y in current], 1.2)
    if simplified and simplified[0] == simplified[-1]:
        simplified = simplified[:-1]
    return simplified or [(int(x), int(y)) for x, y in points]


def _outline_xy(contour: list[tuple[int, int]], scale: float) -> list[tuple[float, float]]:
    center = (WORK - 1) / 2
    raw = [((x - center) / center, (center - y) / center) for x, y in contour]
    cx = sum(point[0] for point in raw) / len(raw)
    cy = sum(point[1] for point in raw) / len(raw)
    shifted = [(x - cx, y - cy) for x, y in raw]
    furthest = max(math.hypot(x, y) for x, y in shifted) or 1.0
    gain = scale / furthest
    outline = [(x * gain, y * gain) for x, y in shifted]
    if outline[0] != outline[-1]:
        outline.append(outline[0])
    return outline


def _radius_table(outline: list[tuple[float, float]]) -> list[float]:
    """Outermost radius at each of 360 degrees. The subject becomes one bold shape."""
    radii = [0.0] * 360
    for (x0, y0), (x1, y1) in zip(outline, outline[1:], strict=False):
        # Sample along the edge so a long side still fills every degree it covers.
        pieces = max(1, int(math.dist((x0, y0), (x1, y1)) / 0.01))
        for index in range(pieces + 1):
            fraction = index / pieces
            x = x0 + (x1 - x0) * fraction
            y = y0 + (y1 - y0) * fraction
            radius = math.hypot(x, y)
            degree = int(round(math.degrees(math.atan2(y, x)))) % 360
            if radius > radii[degree]:
                radii[degree] = radius
    for index, radius in enumerate(radii):
        if radius > 0:
            continue
        previous = next(radii[(index - step) % 360] for step in range(1, 360) if radii[(index - step) % 360] > 0)
        nxt = next(radii[(index + step) % 360] for step in range(1, 360) if radii[(index + step) % 360] > 0)
        radii[index] = (previous + nxt) / 2
    return radii


def _radius_at(table: list[float], phi: float) -> float:
    degree = math.degrees(phi) % 360
    index = int(degree) % 360
    nxt = (index + 1) % 360
    fraction = degree - int(degree)
    return table[index] * (1 - fraction) + table[nxt] * fraction


def _compose(
    table: list[float], preset: dict[str, float]
) -> tuple[list[tuple[float, float]], float]:
    """Sweep, trace the outline twice, then flow rows around it.

    Each row starts at the end nearer the ball, so the move between rows is
    about one spacing. A move that runs straight across the row direction is
    the kind of transit the picture should not keep.
    """
    direction = (math.cos(math.radians(preset["angle"])), math.sin(math.radians(preset["angle"])))
    normal = (-direction[1], direction[0])
    end = math.atan2(-normal[1], -normal[0])
    path = _sweep(table, end, preset["sweep"])
    path.extend(_loop(table, end, 0.0))
    path.extend(_loop(table, end, OUTLINE_INSET))
    stray = 0.0
    spacing = preset["spacing"]
    for row in _rows(preset["angle"], spacing, preset["wave"]):
        runs = _flow(row, table)
        if not runs:
            continue
        runs.sort(key=lambda run: min(math.dist(path[-1], point) for point in run))
        for run in runs:
            ordered = _enter(run, path[-1])
            link, penalty = _connect(path[-1], ordered[0], table)
            if penalty > spacing * 2 and _along(path[-1], ordered[0], normal):
                # Rows drawn after this spoke cross it and wipe it out.
                penalty = spacing
            stray = max(stray, penalty)
            path.extend(link)
            path.extend(ordered)
    return path, stray


def _enter(run: list[tuple[float, float]], here: tuple[float, float]) -> list[tuple[float, float]]:
    """The whole run, starting nearest the ball and finishing at the other end.

    Entering in the middle draws out to the far end, then back along the same
    line to the near end, so nothing is skipped and the ball does not jump.
    """
    index = min(range(len(run)), key=lambda item: math.dist(here, run[item]))
    if index <= 1:
        return run
    if index >= len(run) - 2:
        return list(reversed(run))
    if math.dist(run[index], run[-1]) >= math.dist(run[index], run[0]):
        return run[index:] + run[-2::-1]
    return run[index::-1] + run[1:]


def _along(
    start: tuple[float, float], end: tuple[float, float], normal: tuple[float, float]
) -> bool:
    """True when the move is about perpendicular to the background rows."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    return abs(dx / length * normal[0] + dy / length * normal[1]) >= 0.7


def _sweep(table: list[float], end: float, spacing: float) -> list[tuple[float, float]]:
    samples = [_radius_at(table, 2 * math.pi * index / 180) for index in range(180)]
    mean = sum(samples) / len(samples)
    turns = max(1.0, mean / spacing)
    total = 2 * math.pi * turns
    points = [(0.0, 0.0)]
    travelled = 0.0
    while travelled < total:
        travelled += STEP / max((travelled / total) * mean, 0.03)
        fraction = min(1.0, travelled / total)
        phi = end - total + total * fraction
        radius = fraction * _radius_at(table, phi)
        points.append((radius * math.cos(phi), radius * math.sin(phi)))
    tip = _radius_at(table, end)
    points.append((tip * math.cos(end), tip * math.sin(end)))
    return points


def _loop(table: list[float], phi0: float, inset: float) -> list[tuple[float, float]]:
    samples = max(48, int(2 * math.pi * 0.7 / STEP))
    points: list[tuple[float, float]] = []
    for index in range(samples + 1):
        phi = phi0 + 2 * math.pi * index / samples
        radius = max(0.02, _radius_at(table, phi) - inset)
        points.append((radius * math.cos(phi), radius * math.sin(phi)))
    return points


def _rows(angle: float, spacing: float, wave: float) -> list[list[tuple[float, float]]]:
    direction = (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
    normal = (-direction[1], direction[0])
    rows: list[list[tuple[float, float]]] = []
    offset = -RIM
    band = 0
    while offset <= RIM:
        position = -1.2
        row: list[tuple[float, float]] = []
        while position <= 1.2:
            wobble = wave * math.sin(2.6 * position + 0.4 * band)
            x = direction[0] * position + normal[0] * (offset + wobble)
            y = direction[1] * position + normal[1] * (offset + wobble)
            row.append((x, y))
            position += STEP
        rows.append(row)
        offset += spacing
        band += 1
    return rows


def _contains(point: tuple[float, float], table: list[float]) -> bool:
    radius = math.hypot(*point)
    if radius < 1e-6:
        return True
    return radius <= _radius_at(table, math.atan2(point[1], point[0])) * 0.99


def _flow(row: list[tuple[float, float]], table: list[float]) -> list[list[tuple[float, float]]]:
    """Drop the part of a row inside the subject and walk the outline instead."""
    runs: list[list[tuple[float, float]]] = []
    run: list[tuple[float, float]] = []
    skipping = False
    entry: tuple[float, float] | None = None
    previous: tuple[float, float] | None = None
    for point in row:
        on_table = math.hypot(*point) <= RIM
        hit = on_table and _contains(point, table)
        if not on_table:
            if run:
                runs.append(run)
                run = []
            skipping = False
            entry = None
            previous = point
            continue
        if hit and not skipping:
            entry = previous if previous is not None and math.hypot(*previous) <= RIM else point
            skipping = True
        elif skipping and not hit:
            if entry is not None:
                run.extend(_around(entry, point, table))
            skipping = False
            entry = None
        if not skipping:
            run.append(point)
        previous = point
    if run:
        runs.append(run)
    return [item for item in runs if len(item) >= 2]


def _around(
    start: tuple[float, float], end: tuple[float, float], table: list[float]
) -> list[tuple[float, float]]:
    """Outline from where a row enters to where it leaves, on the row's side."""
    phi_a = math.atan2(start[1], start[0])
    phi_b = math.atan2(end[1], end[0])
    cross = (end[0] - start[0]) * (0 - start[1]) - (end[1] - start[1]) * (0 - start[0])
    delta = (phi_b - phi_a) % (2 * math.pi)
    if cross <= 0:
        delta -= 2 * math.pi
    samples = max(2, int(abs(delta) * 0.75 / STEP))
    return [
        (
            _radius_at(table, phi_a + delta * index / samples)
            * math.cos(phi_a + delta * index / samples),
            _radius_at(table, phi_a + delta * index / samples)
            * math.sin(phi_a + delta * index / samples),
        )
        for index in range(1, samples + 1)
    ]


def _connect(
    start: tuple[float, float],
    end: tuple[float, float],
    table: list[float],
) -> tuple[list[tuple[float, float]], float]:
    """Join two runs. A retrace of the outline or the rim is not a stray line."""
    gap = math.dist(start, end)
    if gap <= STEP * 1.5:
        return _line(start, end)[1:], 0.0
    if abs(math.hypot(*start) - RIM) < 0.06 and abs(math.hypot(*end) - RIM) < 0.06:
        return _rim_arc(start, end), 0.0
    if _on_outline(start, table) and _on_outline(end, table):
        return _around(start, end, table), 0.0
    return _line(start, end)[1:], gap


def _on_outline(point: tuple[float, float], table: list[float]) -> bool:
    radius = math.hypot(*point)
    if radius < 1e-6:
        return False
    return abs(radius - _radius_at(table, math.atan2(point[1], point[0]))) <= 0.05


def _line(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    pieces = max(1, math.ceil(math.dist(start, end) / STEP))
    return [
        (
            start[0] + (end[0] - start[0]) * index / pieces,
            start[1] + (end[1] - start[1]) * index / pieces,
        )
        for index in range(pieces + 1)
    ]


def _rim_arc(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    angle0 = math.atan2(start[1], start[0])
    delta = (math.atan2(end[1], end[0]) - angle0 + math.pi) % (2 * math.pi) - math.pi
    pieces = max(1, int(abs(delta) * RIM / STEP))
    return [
        (RIM * math.cos(angle0 + delta * index / pieces), RIM * math.sin(angle0 + delta * index / pieces))
        for index in range(1, pieces + 1)
    ]


def _clamp_disc(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    clamped: list[tuple[float, float]] = []
    for x, y in points:
        radius = math.hypot(x, y)
        if radius > 1:
            x, y = x / radius, y / radius
        clamped.append((x, y))
    return clamped


def _thin(points: list[tuple[float, float]], spacing: float) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points
    kept = [points[0]]
    for theta, rho in points[1:]:
        prev_theta, prev_rho = kept[-1]
        distance = math.hypot(rho - prev_rho, (theta - prev_theta) * max(rho, prev_rho, 0.02))
        if distance >= spacing:
            kept.append((theta, rho))
    if kept[-1] != points[-1]:
        kept.append(points[-1])
    return kept


def _score_sand(sand: Sand, outline: list[tuple[float, float]]) -> tuple[float, float]:
    """Outline grooves that survived, and how much of the disc the ball touched."""
    p = sand.p
    groove = sand.h < (p.depth - 0.006)
    hits = 0
    checked = 0
    for x, y in outline[:: max(1, len(outline) // 80)]:
        ci = int(round((p.extent - y) / sand.dx - 0.5))
        cj = int(round((x + p.extent) / sand.dx - 0.5))
        if not (0 <= ci < p.n and 0 <= cj < p.n):
            continue
        checked += 1
        i0, i1 = max(0, ci - 2), min(p.n, ci + 3)
        j0, j1 = max(0, cj - 2), min(p.n, cj + 3)
        if bool(groove[i0:i1, j0:j1].any()):
            hits += 1
    recognizable = hits / checked if checked else 0.0
    disturbed = np.abs(sand.h - p.depth) > 0.004
    inside = sand.R <= RIM
    coverage = float(disturbed[inside].mean()) if int(inside.sum()) else 0.0
    return recognizable, coverage


def _composite(recognizable: float, coverage: float, stray: float) -> float:
    """Prefer a readable outline, a filled table, and no long transit."""
    if coverage < 0.35:
        cover = coverage / 0.35
    else:
        cover = 1.0
    stray_score = 1.0 - min(1.0, stray / 0.4)
    return 0.5 * recognizable + 0.3 * cover + 0.2 * stray_score
