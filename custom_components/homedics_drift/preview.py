"""Sand preview pictures for uploaded patterns.

Pillow draws the picture. Home Assistant already ships Pillow, so this file
does not add a dependency of its own. Grooves are dark on tan sand, with a
soft shadow so a dense path still reads as a track.
"""

from __future__ import annotations

import io
import math


def render_thr(text: str, size: int = 256) -> bytes:
    """Preview the same points that will be uploaded."""
    from .patterns import densify, parse_thr

    return render_preview(densify(parse_thr(text)), size=size)


def render_preview(points: list[tuple[float, float]], size: int = 256) -> bytes:
    """Draw densified polar points as grooves in tan sand. Returns a PNG."""
    from PIL import Image, ImageDraw, ImageFilter

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
        plot: list[tuple[float, float]] = []
        for theta, rho in points:
            clamped = max(0.0, min(1.0, rho))
            plot.append(
                (
                    center + math.cos(theta) * clamped * radius,
                    center - math.sin(theta) * clamped * radius,
                )
            )
        shadow = Image.new("L", (size, size), 0)
        ImageDraw.Draw(shadow).line(plot, fill=210, width=max(2, size // 70))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, size // 90)))
        groove = Image.new("L", (size, size), 0)
        ImageDraw.Draw(groove).line(plot, fill=255, width=max(1, size // 150))
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
