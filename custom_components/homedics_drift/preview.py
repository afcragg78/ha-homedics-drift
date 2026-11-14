"""Sand preview pictures for uploaded patterns.

Pillow draws the picture. Home Assistant already ships Pillow, so this file
does not add a dependency of its own. Grooves are dark on tan sand, with a
soft shadow so a dense path still reads as a track.
"""

from __future__ import annotations

import io
import math


def render_thr(text: str, size: int = 256) -> bytes:
    """Preview the same points that will be uploaded.

    The groove follows linear theta-rho motion, which is how the ball moves.
    """
    from .patterns import parse_thr

    return render_preview(parse_thr(text), size=size)


def render_preview(points: list[tuple[float, float]], size: int = 256) -> bytes:
    """Draw polar points as grooves in tan sand. Returns a PNG.

    Samples are filled in by linear steps in theta and rho before the groove
    is drawn. A jump of 2π is an orbit on the table, and it is an orbit here.
    """
    from PIL import Image, ImageDraw, ImageFilter

    from .patterns import densify

    points = densify(points)

    margin = max(6, size // 16)
    center = (size - 1) / 2
    radius = center - margin
    sand = Image.new("RGB", (size, size))
    pixels = sand.load()
    for y in range(size):
        for x in range(size):
            distance = math.hypot(x - center, y - center) / max(radius, 1)
            if distance > 1:
                pixels[x, y] = (28, 24, 22)
                continue
            shade = distance * distance
            pixels[x, y] = (
                int(236 - 52 * shade),
                int(204 - 58 * shade),
                int(158 - 46 * shade),
            )
    if len(points) >= 2:
        # Rim travel (rho near 1) is only how the ball walks between strokes.
        plot_runs = _runs_inside(points, rim=0.955)
        shadow = Image.new("L", (size, size), 0)
        shadow_draw = ImageDraw.Draw(shadow)
        groove = Image.new("L", (size, size), 0)
        groove_draw = ImageDraw.Draw(groove)
        width_shadow = max(2, size // 70)
        width_groove = max(1, size // 150)
        for run in plot_runs:
            plot = [
                (
                    center + math.cos(theta) * max(0.0, min(1.0, rho)) * radius,
                    center - math.sin(theta) * max(0.0, min(1.0, rho)) * radius,
                )
                for theta, rho in run
            ]
            if len(plot) >= 2:
                shadow_draw.line(plot, fill=210, width=width_shadow)
                groove_draw.line(plot, fill=255, width=width_groove)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, size // 90)))
        shadow_px = shadow.load()
        groove_px = groove.load()
        for y in range(size):
            for x in range(size):
                if math.hypot(x - center, y - center) > radius:
                    continue
                soft = shadow_px[x, y] / 255
                hard = groove_px[x, y] / 255
                red, green, blue = pixels[x, y]
                red = int(red * (1 - 0.42 * soft))
                green = int(green * (1 - 0.46 * soft))
                blue = int(blue * (1 - 0.4 * soft))
                red = int(red * (1 - 0.75 * hard) + 48 * hard)
                green = int(green * (1 - 0.75 * hard) + 34 * hard)
                blue = int(blue * (1 - 0.75 * hard) + 22 * hard)
                pixels[x, y] = (red, green, blue)
    draw = ImageDraw.Draw(sand)
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=(120, 86, 58),
        width=max(1, size // 80),
    )
    buffer = io.BytesIO()
    sand.save(buffer, format="PNG")
    return buffer.getvalue()


def _runs_inside(points, rim):
    """Split the path where it only travels along the table edge."""
    runs = []
    run = []
    for point in points:
        if point[1] >= rim:
            if len(run) >= 2:
                runs.append(run)
            run = []
        else:
            run.append(point)
    if len(run) >= 2:
        runs.append(run)
    return runs
