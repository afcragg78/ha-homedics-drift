"""Sand preview pictures for uploaded patterns.

Pillow draws the picture. Home Assistant already ships Pillow, so this file
does not add a dependency of its own.
"""

from __future__ import annotations

import io
import math


def render_thr(text: str, size: int = 256) -> bytes:
    """Preview the same points that will be uploaded."""
    from .patterns import densify, parse_thr

    return render_preview(densify(parse_thr(text)), size=size)


def render_preview(points: list[tuple[float, float]], size: int = 256) -> bytes:
    """Draw densified polar points as grooves in dark sand. Returns a PNG."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (size, size), (24, 18, 14))
    draw = ImageDraw.Draw(image)
    margin = 10
    draw.ellipse((margin, margin, size - margin - 1, size - margin - 1), fill=(96, 72, 48))
    if len(points) >= 2:
        center = size / 2
        radius = center - margin - 6
        plot: list[tuple[float, float]] = []
        for theta, rho in points:
            clamped = max(0.0, min(1.0, rho))
            plot.append(
                (
                    center + math.cos(theta) * clamped * radius,
                    center - math.sin(theta) * clamped * radius,
                )
            )
        draw.line(plot, fill=(222, 196, 150), width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
