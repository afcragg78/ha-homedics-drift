# MIT License
#
# Copyright (c) 2026 Altimix LLC
#
# Ported from Josh Lannin's Drifted sand twin:
# https://github.com/joshlannin/drifted/blob/main/tools/twin/sand.py
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Digital twin of the sand: a heightfield the ball ploughs, rendered to a PNG.

Units are table radii. The defaults are the ones Drifted fitted to webcam
photos of a 16 inch table (ball radius 0.034, half buried, sand settling near
39 degrees, the ball lagging the magnet by about 0.021). Long moves are
spirals in polar coordinates, which is how the table actually travels.

OpenCV is not used. The picture is written with Pillow. The grid uses numpy,
which Home Assistant's image already constrains and which this integration
installs when it is missing. The ring light is fewer lamps than Drifted's
tool, so a preview can finish inside Home Assistant's executor.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class Params:
    """Sand and ball. Distances are table radii."""

    n: int = 200
    extent: float = 1.16
    rim: float = 1.12
    depth: float = 0.03
    noise: float = 0.0012
    ball: float = 0.034
    sink: float = 0.5
    spread: float = 0.845
    ahead: float = 1.0
    repose: float = 39.0
    lag: float = 0.021
    cone: float = 1.0
    sided: float = 0.75
    seed: int = 1


class Sand:
    """One table of sand. ``draw`` can be called again to draw over it."""

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        p = self.p
        self.dx = 2 * p.extent / p.n
        coords = (np.arange(p.n) + 0.5) * self.dx - p.extent
        self.X, self.Y = np.meshgrid(coords, -coords)
        self.R = np.hypot(self.X, self.Y)
        self.inside = self.R <= p.rim
        rng = np.random.default_rng(p.seed)
        height = p.depth + p.noise * _blur(rng.standard_normal((p.n, p.n)), 2)
        self.h = np.where(self.inside, height, p.depth)
        self.ballpos: tuple[float, float] | None = None
        reach = p.ball / self.dx
        self.w = int(math.ceil(reach * (2.2 + p.spread)))

    def draw(self, xy: list[tuple[float, float]]) -> Sand:
        """Plough ``xy`` in order. The ball starts where the previous draw stopped."""
        p = self.p
        step = self.dx
        points = list(xy)
        if self.ballpos is not None:
            points = [self.ballpos, *points]
        if len(points) < 2:
            return self
        path = _table_path(points, step)
        if p.lag > 0:
            path = _trail(path, p.lag)
        floor = p.depth - p.sink * p.ball
        previous: tuple[float, float] | None = self.ballpos
        for x, y in path:
            self._stamp(x, y, previous, floor)
            previous = (x, y)
        self.ballpos = previous
        self.relax(2)
        return self

    def _stamp(
        self,
        x: float,
        y: float,
        previous: tuple[float, float] | None,
        floor: float,
    ) -> None:
        p, w = self.p, self.w
        ci = int(round((p.extent - y) / self.dx - 0.5))
        cj = int(round((x + p.extent) / self.dx - 0.5))
        if ci - w < 0 or cj - w < 0 or ci + w >= p.n or cj + w >= p.n:
            return
        window = self.h[ci - w : ci + w + 1, cj - w : cj + w + 1]
        ky, kx = np.mgrid[-w : w + 1, -w : w + 1]
        kx = kx * self.dx
        ky = -ky * self.dx
        distance = np.hypot(kx, ky)
        core = distance < p.ball
        cap = np.where(
            core,
            p.ball - np.sqrt(np.maximum(p.ball**2 - distance**2, 0)),
            0,
        )
        band = (distance >= p.ball) & (distance <= p.ball * (1 + p.spread))
        edge = p.ball * (1 + p.spread)
        span = max(edge - p.ball, 1e-9)
        band_w = np.where(band, np.clip((edge - distance) / span, 0, None), 0)
        cut = np.where(core, np.maximum(window - (floor + cap), 0), 0)
        moved = float(cut.sum())
        if moved <= 0:
            return
        window -= cut
        if previous is not None and (x, y) != previous:
            dxm, dym = x - previous[0], y - previous[1]
            length = math.hypot(dxm, dym) or 1.0
            ux, uy = dxm / length, dym / length
            along = (kx * ux + ky * uy) / (distance + 1e-12)
            weight = band_w * (
                (1 - p.ahead) * (1 - along**2) + p.ahead * np.clip(along, 0, None) ** p.cone
            )
        else:
            ux = uy = 0.0
            weight = band_w
        inside = self.inside[ci - w : ci + w + 1, cj - w : cj + w + 1]
        weight = weight * inside
        total = float(weight.sum())
        if total <= 0:
            return
        if p.sided > 0 and previous is not None and (x, y) != previous:
            left = 0.5 * (1 + np.tanh((ky * ux - kx * uy) / (0.15 * p.ball)))
            cut_left = float((cut * left).sum())
            added = (1 - p.sided) * moved * weight / total
            for part, side in ((cut_left, left), (moved - cut_left, 1 - left)):
                sided = weight * side
                sided_total = float(sided.sum())
                if sided_total > 0:
                    added = added + p.sided * part * sided / sided_total
                else:
                    added = added + p.sided * part * weight / total
        else:
            added = moved * weight / total
        window += added

    def relax(self, iterations: int = 2) -> None:
        """Sand steeper than the angle of repose slumps downhill."""
        p = self.p
        height = self.h
        inside = self.inside
        limit = math.tan(math.radians(p.repose)) * self.dx
        for _ in range(iterations):
            for axis in (0, 1):
                delta = np.diff(height, axis=axis)
                if axis == 0:
                    mask = inside[1:, :] & inside[:-1, :]
                else:
                    mask = inside[:, 1:] & inside[:, :-1]
                excess = np.where(mask, np.sign(delta) * np.maximum(np.abs(delta) - limit, 0) * 0.25, 0)
                if axis == 0:
                    height[:-1, :] += excess
                    height[1:, :] -= excess
                else:
                    height[:, :-1] += excess
                    height[:, 1:] -= excess

    def render(self) -> np.ndarray:
        """Grey image, 0..1, row 0 at the top (+y). Outside the sand is dark."""
        p = self.p
        gy, gx = np.gradient(self.h, self.dx)
        gy = -gy
        normal = np.sqrt(1 + gx**2 + gy**2)
        nx, ny, nz = -gx / normal, -gy / normal, 1 / normal
        ring = np.zeros_like(self.h)
        lamps = 24
        for index in range(lamps):
            angle = 2 * math.pi * index / lamps
            lx = p.rim * 1.01 * math.cos(angle) - self.X
            ly = p.rim * 1.01 * math.sin(angle) - self.Y
            lz = 0.05
            distance = np.sqrt(lx**2 + ly**2 + lz**2)
            ring += np.clip((nx * lx + ny * ly + nz * lz) / distance, 0, None) / distance
        ring /= lamps
        radius = max(1, int(round(p.ball / self.dx)))
        cavity = (self.h - _blur(self.h, radius)) / p.ball
        slope = 1 - nz
        image = ring + 0.6 * cavity - 1.5 * slope
        sand = image[self.inside]
        low, high = np.percentile(sand, [1, 99])
        span = float(np.ptp(np.array([low, high]))) + 1e-9
        image = (image - low) / span
        return np.where(self.inside, np.clip(image, 0, 1), 0.08)


def render_png(
    xy: list[tuple[float, float]],
    *,
    n: int = 200,
    size: int = 480,
    seed: int = 1,
) -> tuple[bytes, Sand]:
    """Draw ``xy`` and return a warm sand PNG plus the heightfield."""
    sand = Sand(Params(n=n, seed=seed))
    sand.draw(xy)
    return _png(sand, size), sand


def _png(sand: Sand, size: int) -> bytes:
    grey = (np.clip(sand.render(), 0, 1) * 255).astype(np.uint8)
    image = Image.fromarray(grey, mode="L")
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    palette: list[int] = []
    for level in range(256):
        tone = level / 255
        palette.extend(
            (
                int(48 + tone * 188),
                int(32 + tone * 168),
                int(20 + tone * 120),
            )
        )
    image.putpalette(palette)
    picture = image.convert("RGB")
    if sand.ballpos is not None:
        _dot(picture, sand, size)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


def _dot(picture: Image.Image, sand: Sand, size: int) -> None:
    """The ball, sitting where the path ended."""
    assert sand.ballpos is not None
    x, y = sand.ballpos
    p = sand.p
    column = int((x + p.extent) / (2 * p.extent) * (size - 1))
    row = int((p.extent - y) / (2 * p.extent) * (size - 1))
    radius = max(2, int(p.ball / (2 * p.extent) * size))
    pixels = picture.load()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            px, py = column + dx, row + dy
            if 0 <= px < size and 0 <= py < size:
                pixels[px, py] = (36, 28, 24)


def _table_path(xy: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    """Straight steps in (theta, rho). A long move is a spiral, not a chord."""
    polar: list[tuple[float, float]] = []
    previous: float | None = None
    for x, y in xy:
        theta, radius = math.atan2(y, x), min(1.0, math.hypot(x, y))
        if previous is not None:
            theta = previous + (theta - previous + math.pi) % (2 * math.pi) - math.pi
        polar.append((theta, radius))
        previous = theta
    start = polar[0]
    out = [(start[1] * math.cos(start[0]), start[1] * math.sin(start[0]))]
    for (theta0, radius0), (theta1, radius1) in zip(polar, polar[1:]):
        length = math.hypot(radius1 - radius0, max(radius0, radius1) * (theta1 - theta0))
        pieces = max(1, int(math.ceil(length / step)))
        for index in range(1, pieces + 1):
            fraction = index / pieces
            theta = theta0 + (theta1 - theta0) * fraction
            radius = radius0 + (radius1 - radius0) * fraction
            out.append((radius * math.cos(theta), radius * math.sin(theta)))
    return out


def _trail(points: list[tuple[float, float]], lag: float) -> list[tuple[float, float]]:
    """The ball follows the magnet on a short string, so it cuts corners."""
    bx, by = points[0]
    out = [(bx, by)]
    for x, y in points[1:]:
        distance = math.hypot(x - bx, y - by)
        if distance > lag:
            fraction = (distance - lag) / distance
            bx = bx + (x - bx) * fraction
            by = by + (y - by) * fraction
        out.append((bx, by))
    return out


def _blur(values: np.ndarray, radius: int) -> np.ndarray:
    """Three box blurs, close to a Gaussian. Edges are padded."""
    array = values
    for _ in range(3):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (radius + 1, radius)
            cumulative = np.cumsum(np.pad(array, pad, mode="edge"), axis=axis)
            if axis == 0:
                array = (cumulative[2 * radius + 1 :, :] - cumulative[: -2 * radius - 1, :]) / (
                    2 * radius + 1
                )
            else:
                array = (cumulative[:, 2 * radius + 1 :] - cumulative[:, : -2 * radius - 1]) / (
                    2 * radius + 1
                )
    return array
