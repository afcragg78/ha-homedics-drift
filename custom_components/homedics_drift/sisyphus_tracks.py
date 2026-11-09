"""Curated Sisyphus tracks shipped with this integration.

The files in ``sisyphus/`` are converted from Bruce Shapiro's MIT-licensed
tracks at https://github.com/Dithermaster/sisyphus (Copyright Bruce Shapiro).
See ``sisyphus/LICENSE``.
"""

from __future__ import annotations

from pathlib import Path

from .patterns import densify, parse_thr

CATALOG: tuple[tuple[str, str], ...] = (
    ("Cells", "dither_cells"),
    ("Eccentric Erase", "dither_eccentricerase"),
    ("Gears", "dither_gears"),
    ("Gosper Curve", "dither_gosper4"),
    ("Hypno Grid", "dither_hypnogrid"),
    ("Your Move", "dither_itsyourmove"),
    ("Sisyphus Nautilus", "dither_nautilus"),
    ("Parallel Field", "dither_parallel"),
    ("Sierpinski", "dither_sierpinski6"),
    ("Sierpinski Eight", "dither_sierpinski8"),
    ("Infinity Turn", "dither_sisinfturn"),
    ("Strange Thing", "dither_strangthang"),
    ("Sunburst", "dither_sunburst"),
    ("Triangle Weave", "dither_tri4"),
    ("Wormhole", "dither_wormhole"),
    ("Yin Yang", "dither_yinyang"),
)


def track_polar(key: str) -> list[tuple[float, float]]:
    """Theta-rho points for one converted track, from the centre to the rim."""
    path = Path(__file__).parent / "sisyphus" / f"{key}.thr"
    points = parse_thr(path.read_text(encoding="utf-8"))
    if points[0][1] > 0.001:
        head = densify([(points[0][0], 0.0), points[0]], max_step=0.02)
        points = head[:-1] + points
    if abs(points[-1][1] - 1.0) > 0.001:
        tail = densify([points[-1], (points[-1][0], 1.0)], max_step=0.02)
        points = points + tail[1:]
    points[0] = (points[0][0], 0.0)
    points[-1] = (points[-1][0], 1.0)
    return points
