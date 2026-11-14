#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2026 Altimix LLC
#
# Vendored from Josh Lannin's Drifted designs/weather.py:
# https://github.com/joshlannin/drifted/blob/main/designs/weather.py
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

"""Weather: an emblem for the day's conditions, under the forecast high in big digits.

    sunny         a sun with pointed rays; ripples spread from it across the table
    partlycloudy  that sun with some rays behind a cloud
    cloudy        two clouds floating in drifting wind lines
    fog           flat banks of mist, in horizontal wavy bands
    rain          a cloud and raindrops, left smooth in slanting rain
    thunderstorm  a cloud, a bold lightning bolt, and a few slanted rain lines
    snow          a big snowflake and two small ones, in gently drifting lines
    clear_night   a crescent moon and a few small stars
    windy         four long wavy lines under the temperature, each ending in a round curl

Sun, clouds, rain, snow, and the temperature digits are Josh Lannin's. The other
five pictures use the same construction.

Shapes and the temperature sit on swept, smooth sand; everything else is textured. Background
lines flow around each shape instead of through it, which is what outlines the shape. The ball
never lifts, so the picture is one path, drawn in this order:

1. each shape: a tight spiral that sweeps it smooth, its outline (twice), then its detail;
2. the background, row by row. The rows also wipe out the moves between shapes, as long as those
   moves cross them, so shapes are ordered to make that happen;
3. the temperature panel across the top: swept smooth, then bold digits, each drawn three times
   side by side so it stands out from the sweep lines around it.

The drawing ends inside the panel. `--update` makes a short segment that re-sweeps just the
panel and writes a new number, leaving the rest of the picture alone.

Usage:
  python3 designs/weather.py sunny 72 [OUT]       full picture (about 16 minutes to draw)
  python3 designs/weather.py --update 75 [OUT]    temperature only (about 6 minutes)
Temperatures can be -99..199. OUT ending in .json is an `xy` drawing for driftd's /show;
otherwise it's HoMedics Drift .txt. --rotate turns the picture to match how the table sits.
Digits are 0.45 radii tall for one or two digits, a little less for three.
"""
import argparse
import json
import math

STEP = 0.01     # path sampling, in table radii
RIM = 0.96      # background rows reach this far out
BALL = 0.07     # groove width
SWEEP = 0.05    # spacing of the sweep rows above the number
SHAPE_SWEEP = 0.04  # spacing of the spiral that sweeps each shape smooth

# Temperature panel: the cap of the table above PANEL_Y.
PANEL_Y = 0.12
PANEL_RIM = 0.92  # the panel's sweep stops short of the wall, where swept sand piles up
TEXT_RIM = 0.88   # outer edge of the number's outermost groove
BASELINE = PANEL_Y + 0.08
CAP = 0.45      # digit height, shrunk if the number doesn't fit
BOLD = 0.03     # digits are drawn three times, this far either side of the stroke
GAP = 0.19      # between digits, centre to centre of the strokes (> BALL + 2 * BOLD)
BAND_SWEEP = 0.035  # finer sweep around the digits, so they stand out from it
DEGREE = 0.065  # radius of the degree ring


def arc(cx, cy, rx, ry, a0, a1, n=None):
    n = n or max(4, int(abs(a1 - a0) / 6))
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def polar(c, r, phi):
    return (c[0] + r * math.cos(phi), c[1] + r * math.sin(phi))


def cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


# ---------------------------------------------------------------------------------------------
# Shapes

class Shape:
    """A star-shaped region around `c` with edge radius(phi). The background flows around it."""

    def __init__(self, c, radius, snap=None, detail=None):
        self.c, self.radius = c, radius
        self.snap = snap or (lambda phi: phi)        # preferred exit angle near phi
        self.detail = detail or (lambda phi: [])     # drawn after sweeping; starts and ends at edge(phi)
        self.rmax = max(radius(2 * math.pi * i / 720) for i in range(720))

    def edge(self, phi, scale=1.0):
        return polar(self.c, scale * self.radius(phi), phi)

    def angle(self, p):
        return math.atan2(p[1] - self.c[1], p[0] - self.c[0])

    def contains(self, p):
        d = math.dist(p, self.c)
        return d < self.rmax and d < self.radius(self.angle(p))

    def walk(self, phi0, delta):
        n = max(2, int(abs(delta) * self.rmax / STEP))
        return [self.edge(phi0 + delta * i / n) for i in range(1, n + 1)]

    def around(self, a, b):
        """Edge points from where a row enters (a) to where it leaves (b), on the row's side."""
        phi_a, phi_b = self.angle(a), self.angle(b)
        ccw = cross((b[0] - a[0], b[1] - a[1]), (self.c[0] - a[0], self.c[1] - a[1])) > 0
        delta = (phi_b - phi_a) % (2 * math.pi)
        return self.walk(phi_a, delta if ccw else delta - 2 * math.pi)

    def draw(self, toward):
        """Sweep smooth from the centre out, trace the outline twice (once just inside it) so the
        shape stands out, then add the detail. Ends on the edge."""
        end = self.snap(math.atan2(toward[1] - self.c[1], toward[0] - self.c[0]))
        # Turns are packed closer where the edge is nearer the centre; size them for a typical radius.
        mean = sum(self.radius(2 * math.pi * i / 360) for i in range(360)) / 360
        total = 2 * math.pi * math.ceil((mean + self.rmax) / 2 / SHAPE_SWEEP)
        pts, t = [], 0.0
        while t < total:
            pts.append(self.edge(end - total + t, t / total))
            t += STEP / max(t / total * self.rmax, 0.03)
        pts += [self.edge(end)] + self.walk(end, 2 * math.pi)
        inset = [self.edge(end - 2 * math.pi * i / 720, 1 - BALL / 2 / self.radius(end - 2 * math.pi * i / 720))
                 for i in range(721)]
        return pts + inset + [self.edge(end)] + self.detail(end)


def sun(c, r_in=0.22, r_out=0.36, rays=12, disc=0.17):
    def radius(phi):
        u = (phi * rays / (2 * math.pi)) % 1
        return r_in + (r_out - r_in) * abs(2 * u - 1)   # tips at u = 0, valleys at u = 0.5

    def snap(phi):  # leave through a valley, so the way in to the disc is short
        return (math.floor(phi * rays / (2 * math.pi)) + 0.5) * 2 * math.pi / rays

    def detail(phi):
        n = int(2 * math.pi * disc / STEP)
        return [polar(c, disc, phi + 2 * math.pi * i / n) for i in range(n + 1)] + [polar(c, r_in, phi)]

    return Shape(c, radius, snap, detail)


def cloud(c, w, h, lobes=3, phase=1.0):
    def radius(phi):
        s = math.sin(phi)
        a, b = w / 2, h * (0.55 if s >= 0 else 0.30)    # puffy top, flatter bottom
        base = a * b / math.hypot(b * math.cos(phi), a * math.sin(phi))
        if s > 0:
            return base * (1 + 0.5 * abs(math.sin(lobes * phi + phase)) ** 0.7 * s ** 0.3)
        return base * (1 + 0.05 * abs(math.sin(3 * phi + phase)))

    return Shape(c, radius)


def drop(c, a=0.1, tip=0.26):
    """A raindrop: a round bottom of radius a, pointed tip `tip` above its centre."""
    cone = math.acos(a / tip)

    def radius(phi):
        off = abs((phi - math.pi / 2 + math.pi) % (2 * math.pi) - math.pi)   # angle from straight up
        return a / math.cos(off - cone) if off < cone else a

    return Shape(c, radius)


def flake(c, r, tilt=math.pi / 2, twigs=True):
    """Snowflake: a hexagon swept smooth, with an arm out to each corner and, on big flakes,
    a pair of twigs on each arm."""
    step = math.pi / 3
    length = 0.9 * r

    def radius(phi):  # hexagon with corners on the arms
        d = (phi - tilt) % step - step / 2   # angle from the nearest edge's midpoint
        return r * math.cos(step / 2) / math.cos(d)

    def snap(phi):  # leave along an arm
        return tilt + round((phi - tilt) / step) * step

    def arm(phi):
        tip = polar(c, length, phi)
        if not twigs:
            return [tip, c]
        b = polar(c, 0.5 * length, phi)
        twig = 0.32 * length
        return [b, polar(b, twig, phi + 0.8), b, polar(b, twig, phi - 0.8), b, tip, c]

    def detail(phi):
        pts = [c]
        for k in range(1, 7):
            pts += arm(phi + k * step)
        return pts[:-1] + [polar(c, r, phi)]   # the last arm runs on out to the corner

    return Shape(c, radius, snap, detail)


def _edge_radius(vertices):
    """Radius of a polygon that is star-shaped around the origin. `vertices` go around once."""
    def radius(phi):
        dx, dy = math.cos(phi), math.sin(phi)
        best = None
        for i, (x1, y1) in enumerate(vertices):
            x2, y2 = vertices[(i + 1) % len(vertices)]
            ex, ey = x2 - x1, y2 - y1
            det = dx * ey - dy * ex
            if abs(det) < 1e-12:
                continue
            t = (x1 * ey - y1 * ex) / det
            s = (x1 * dy - y1 * dx) / det
            if t > 1e-5 and -1e-4 <= s <= 1 + 1e-4 and (best is None or t < best):
                best = t
        return best if best is not None else 0.05
    return radius


def bolt(c, scale=0.50):
    """A thick lightning bolt, star-shaped from a point in the middle of the zigzag.

    The corners stay in angle order around that point, so the outline is one jagged
    polygon: wide top, a step to the right, a step to the left, and a long tip.
    """
    # Centred on the star point of the unit bolt, then scaled to the table.
    # Wide enough to read as a bolt, still one polygon around that point.
    raw = (
        (-0.02400, 0.44400),
        (0.34400, 0.44400),
        (0.12000, 0.13120),
        (0.47200, 0.05760),
        (0.15200, -0.18160),
        (0.28000, -0.52200),
        (-0.07200, -0.16320),
        (-0.32800, 0.00240),
        (-0.04000, 0.18640),
    )
    return Shape(c, _edge_radius([(x * scale, y * scale) for x, y in raw]))


def crescent(c, scale=0.86, tilt=0.55):
    """A crescent: the part of one circle outside a second circle that bites into it.

    The shape centre sits in the thick of the crescent, where every direction
    reaches the edge exactly once. `tilt` turns the horns (0 opens to the right).
    """
    outer = (0.22 * scale, 0.0)
    inner = (0.40 * scale, 0.0)
    outer_r, inner_r = 0.34 * scale, 0.28 * scale
    ct, st = math.cos(tilt), math.sin(tilt)
    outer = (outer[0] * ct - outer[1] * st, outer[0] * st + outer[1] * ct)
    inner = (inner[0] * ct - inner[1] * st, inner[0] * st + inner[1] * ct)

    def hits(cx, cy, r, phi):
        dx, dy = math.cos(phi), math.sin(phi)
        b = cx * dx + cy * dy
        disc = b * b - (cx * cx + cy * cy - r * r)
        if disc < 1e-12:
            return []
        root = math.sqrt(disc)
        return [t for t in (b - root, b + root) if t > 1e-5]

    def radius(phi):
        found = []
        for t in hits(outer[0], outer[1], outer_r, phi):
            x, y = t * math.cos(phi), t * math.sin(phi)
            if math.hypot(x - inner[0], y - inner[1]) >= inner_r - 1e-4:
                found.append(t)
        for t in hits(inner[0], inner[1], inner_r, phi):
            x, y = t * math.cos(phi), t * math.sin(phi)
            if math.hypot(x - outer[0], y - outer[1]) <= outer_r + 1e-4:
                found.append(t)
        return min(found) if found else outer_r
    return Shape(c, radius)


def sun_behind(c, cloud_shape, r_in=0.15, r_out=0.32, rays=12, disc=0.13):
    """The sun, with any ray that would enter `cloud_shape` cut off at its edge.

    Drawn before the cloud, so the shortened rays read as going behind it. A hair
    of gap keeps the two shapes from sharing sand; the grooves close that gap.
    """
    def raw(phi):
        u = (phi * rays / (2 * math.pi)) % 1
        return r_in + (r_out - r_in) * abs(2 * u - 1)

    def radius(phi):
        base = raw(phi)
        dx, dy = math.cos(phi), math.sin(phi)
        # The tip can sit past the cloud while the middle of the ray crosses it.
        hit = None
        for i in range(1, 25):
            t = base * i / 24
            if cloud_shape.contains((c[0] + dx * t, c[1] + dy * t)):
                hit = t
                break
        if hit is None:
            return base
        lo, hi = 0.0, hit
        for _ in range(16):
            mid = (lo + hi) / 2
            if cloud_shape.contains((c[0] + dx * mid, c[1] + dy * mid)):
                hi = mid
            else:
                lo = mid
        return max(0.05, lo - 0.02)

    def snap(phi):
        return (math.floor(phi * rays / (2 * math.pi)) + 0.5) * 2 * math.pi / rays

    def detail(phi):
        n = int(2 * math.pi * disc / STEP)
        pts = [polar(c, disc, phi + 2 * math.pi * i / n) for i in range(n + 1)]
        return pts + [polar(c, radius(phi), phi)]

    return Shape(c, radius, snap, detail)


def pebble(c, r):
    """A round hailstone."""
    return Shape(c, lambda phi: r)


def warning_sign(c, r=0.34):
    """A point-up triangle with an exclamation mark, for a weather alert."""
    verts = [
        (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
        for a in (90, 210, 330)
    ]
    edge = _edge_radius(verts)

    def detail(phi):
        bar = line((c[0], c[1] + r * 0.42), (c[0], c[1] + r * 0.02))
        dot_c = (c[0], c[1] - r * 0.22)
        dot = [polar(dot_c, r * 0.07, math.radians(i)) for i in range(0, 361, 24)]
        return bar + dot + [polar(c, edge(phi), phi)]

    return Shape(c, edge, detail=detail)


def band(c, w, h, waves=3.0, phase=0.0):
    """A flat mist bank: a wide, low ellipse with a wavy edge."""
    def radius(phi):
        a, b = w / 2, h / 2
        base = a * b / math.hypot(b * math.cos(phi), a * math.sin(phi))
        return base * (1 + 0.12 * math.sin(waves * phi + phase))
    return Shape(c, radius)


def _spiral(center, r_outer, r_inner, turns, a0, spin):
    """Tight spiral from the outside in. `spin` is the sign of the angle change."""
    arc = abs(turns) * math.pi * (r_outer + r_inner)
    n = max(8, int(arc / STEP))
    pts = []
    for i in range(n + 1):
        t = i / n
        radius = r_outer + (r_inner - r_outer) * t
        ang = a0 + spin * turns * 2 * math.pi * t
        pts.append(polar(center, radius, ang))
    return pts


def _curl_out(join, hang, radius=0.11, turns=1.85):
    """From the eye out to `join`, leaving toward +x. The curl sits above or below the line."""
    if hang == "above":
        center = (join[0], join[1] + radius)
        inward = _spiral(center, radius, 0.036, turns, -math.pi / 2, -1)
    else:
        center = (join[0], join[1] - radius)
        inward = _spiral(center, radius, 0.036, turns, math.pi / 2, 1)
    return inward[::-1]


def _curl_in(join, hang, radius=0.11, turns=1.85):
    """From `join` into the eye, arriving from a line that was heading +x."""
    if hang == "below":
        center = (join[0], join[1] - radius)
        return _spiral(center, radius, 0.036, turns, math.pi / 2, -1)
    center = (join[0], join[1] + radius)
    return _spiral(center, radius, 0.036, turns, -math.pi / 2, 1)


def _swoosh(x0, x1, y, bow=0.012):
    n = max(2, int(abs(x1 - x0) / STEP))
    pts = []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        pts.append((x, y + bow * math.sin(math.pi * t)))
    return pts


def _s_curve(x0, x1, y, amp):
    """An S that starts and ends horizontal, so a curl can sit on either end."""
    n = max(4, int(abs(x1 - x0) / STEP))
    pts = []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        envelope = math.sin(math.pi * t) ** 2
        pts.append((x, y + amp * math.sin(2 * math.pi * t) * envelope))
    return pts


# ---------------------------------------------------------------------------------------------
# Frames: horizontal bands of the table (below the panel) that background rows are clipped to.
# Moves between rows run along the frame's edge.

def line(a, b):
    n = max(1, math.ceil(math.dist(a, b) / STEP))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def nearest(pts, p):
    return min(range(len(pts)), key=lambda i: math.dist(pts[i], p))


def rim_arc(a, b):
    """Round the rim from a to b, the short way."""
    a0 = math.atan2(a[1], a[0])
    d = (math.atan2(b[1], b[0]) - a0 + math.pi) % (2 * math.pi) - math.pi
    n = max(1, int(abs(d) * RIM / STEP))
    return [polar((0, 0), RIM, a0 + d * i / n) for i in range(1, n + 1)] + [b]


class Frame:
    """The part of the table between heights lo and hi (by default, everything below the panel)."""

    def __init__(self, lo=-1.0, hi=PANEL_Y):
        self.lo, self.hi = lo, hi
        self.contour = self._contour()

    def contains(self, p):
        return math.hypot(*p) <= RIM and self.lo <= p[1] < self.hi

    def _contour(self):
        """The edge, counter-clockwise: rim arcs joined by the top (and bottom) edges."""
        def rim(a0, a1):
            n = max(1, int(abs(a1 - a0) * RIM / STEP))
            return [polar((0, 0), RIM, a0 + (a1 - a0) * i / n) for i in range(n + 1)]
        hi = math.asin(self.hi / RIM)
        if self.lo <= -RIM:
            pts = rim(math.pi - hi, 2 * math.pi + hi)
            return pts + line(pts[-1], pts[0])[1:]
        lo = math.asin(self.lo / RIM)
        right, left = rim(lo, hi), rim(math.pi - hi, math.pi - lo)
        return right + line(right[-1], left[0])[1:] + left[1:] + line(left[-1], right[0])[1:-1]

    def link(self, a, b):
        """Points from a to b: along the edge (the short way) when both are on or just inside it,
        round the rim when both are on it, else straight."""
        c = self.contour
        i, j = nearest(c, a), nearest(c, b)
        if math.dist(c[i], a) <= 0.03 and math.dist(c[j], b) <= 0.1:
            n = len(c)
            fwd = [c[(i + k) % n] for k in range((j - i) % n + 1)]
            back = [c[(i - k) % n] for k in range((i - j) % n + 1)]
            return min(fwd, back, key=len) + [b]
        if abs(math.hypot(*a) - RIM) < 0.03 and abs(math.hypot(*b) - RIM) < 0.03:
            return rim_arc(a, b)
        return line(a, b)[1:]


# ---------------------------------------------------------------------------------------------
# Background rows

def parallel_rows(angle, spacing, wave=lambda s, k: 0.0):
    """Lines at `angle` degrees across the whole table, `spacing` apart, optionally wavy."""
    d = (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
    n = (-d[1], d[0])
    rows, k, t = [], 0, -RIM + spacing / 2
    while t < RIM:
        s, row = -1.0, []
        while s <= 1.0:
            off = t + wave(s, k)
            row.append((d[0] * s + n[0] * off, d[1] * s + n[1] * off))
            s += STEP
        rows.append((row, False))
        t, k = t + spacing, k + 1
    return rows


def ring_rows(c, r0, spacing):
    rows, r = [], r0
    while r < math.hypot(*c) + RIM:
        n = int(2 * math.pi * r / STEP)
        rows.append(([polar(c, r, 2 * math.pi * i / n) for i in range(n + 1)], True))
        r += spacing
    return rows


def flow(row, closed, shapes, frame):
    """Split a row into runs inside the frame; where it crosses a shape, go round the edge instead."""
    if closed:
        out = next((i for i, p in enumerate(row) if not frame.contains(p)), None)
        if out is None:
            return [row]
        row = row[out:] + row[1:out + 1]
    runs, run, inside = [], [], None
    for p in row:
        if not frame.contains(p):
            if run:
                runs.append(run)
            run, inside = [], None
            continue
        hit = next((s for s in shapes if s.contains(p)), None)
        if inside is None and hit is not None:
            inside = (hit, run[-1] if run else p)
        elif inside is not None and hit is not inside[0]:
            run += inside[0].around(inside[1], p)
            inside = None
        if inside is None:
            run.append(p)
    if run:
        runs.append(run)
    return runs


def background(path, rows, shapes, frame):
    for row, closed in rows:
        runs = flow(row, closed, shapes, frame)
        if not runs:
            continue
        here = path[-1]
        if len(runs) == 1 and math.dist(runs[0][0], runs[0][-1]) < STEP * 1.5:  # a whole ring
            i = nearest(runs[0], here)
            runs = [runs[0][i:] + runs[0][1:i + 1]]
        elif math.dist(here, runs[-1][-1]) < math.dist(here, runs[0][0]):
            runs = [r[::-1] for r in runs[::-1]]
        for r in runs:
            path += frame.link(path[-1], r[0]) + r
    return path


# ---------------------------------------------------------------------------------------------
# Temperature

# Digits in a box 1 tall: (width, stroke).
DIGITS = {
    "0": (0.6, arc(.3, .5, .3, .5, -90, 270)),
    "1": (0.35, [(.03, .8), (.25, 1), (.25, 0)]),
    "2": (0.6, arc(.3, .72, .3, .28, 160, -40) + [(0, 0), (.6, 0)]),
    "3": (0.6, arc(.3, .75, .27, .25, 150, -90) + arc(.3, .26, .3, .26, 90, -150)),
    "4": (0.62, [(.08, 1), (0, .32), (.45, .32), (.45, 1), (.45, 0), (.45, .32), (.62, .32)]),  # open top
    "5": (0.6, [(.55, 1), (.08, 1), (.05, .55)] + arc(.3, .32, .3, .32, 140, -145)),
    "6": (0.6, arc(.32, .5, .3, .5, 60, 200) + arc(.3, .3, .3, .3, 180, 540)),
    "7": (0.6, [(0, 1), (.6, 1), (.2, 0)]),
    "8": (0.6, arc(.3, .27, .3, .27, -90, 90) + arc(.3, .77, .26, .23, -90, -450)
          + arc(.3, .27, .3, .27, 90, 270)),
    "9": (0.6, arc(.3, .7, .3, .3, 0, 360) + arc(.3, .5, .3, .5, 20, -120)),
}
MINUS = 0.4  # width of the minus bar, in digit heights


def traversals(stroke):
    """Ways to draw a stroke completely, retracing parts of it to start and end where needed."""
    n = len(stroke)
    if math.dist(stroke[0], stroke[-1]) < 1e-6:  # a loop: start anywhere, go once round
        return [stroke[k:] + stroke[1:k + 1] for k in range(0, n - 1, max(1, n // 40))]
    ways = []
    for k in range(0, n, max(1, n // 40)):
        ways.append(stroke[k:] + stroke[::-1][1:])                    # k, out to the end, back to the start
        ways.append(stroke[:k + 1][::-1] + stroke[1:])                # k, back to the start, out to the end
        ways.append(stroke[k:] + stroke[::-1][1:] + stroke[1:k + 1])  # k, both ways, back to k
    return ways + [w[::-1] for w in ways]


def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def offset(path, d):
    """The path shifted sideways by d (to the left of travel)."""
    out = []
    for i, p in enumerate(path):
        a, b = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
        if math.dist(a, b) < 1e-9:  # a turning point where the stroke doubles back
            a, b = (a, p) if math.dist(a, p) > 1e-9 else (p, b)
        n = math.dist(a, b) or 1.0
        out.append((p[0] - (b[1] - a[1]) / n * d, p[1] + (b[0] - a[0]) / n * d))
    return out


def bold(path):
    """Draw the path, back along one side of it and out again along the other: a stroke about
    BALL + 2 * BOLD wide that stands out from the sweep lines around it."""
    path = densify(path)  # so the side flips only where the stroke doubles back, not along a segment
    return path + offset(path, BOLD)[::-1] + offset(path, -BOLD)


def best_traversal(stroke, last):
    """Start at the glyph's left edge if possible (the sweep row leading in comes from the left)
    and, unless it's the last glyph, leave to the right, so the move out stays off the glyph."""
    left, right = min(p[0] for p in stroke), max(p[0] for p in stroke)
    return min(traversals(stroke), key=lambda w: 2 * (w[0][0] - left)
               + (0 if last else 3 * (right - w[-1][0])) + 0.05 * length(w))


def number_width(text, cap):
    w = sum(DIGITS[ch][0] * cap if ch != "-" else MINUS * cap for ch in text) + GAP * len(text)
    return w + 2 * DEGREE


def temperature(value):
    """Strokes for the number and degree sign, centred in the panel, and the digit height."""
    text = str(int(value))
    cap = CAP
    while cap > 0.2:
        w = number_width(text, cap)
        top = BASELINE + cap + BALL / 2 + BOLD
        if math.hypot(w / 2, top) <= TEXT_RIM:  # top corners clear the rim
            break
        cap -= 0.01
    x, strokes = -w / 2, []
    for ch in text:
        cw, stroke = DIGITS[ch] if ch != "-" else (MINUS, [(0, 0.5), (MINUS, 0.5)])
        strokes.append([(x + px * cap, BASELINE + py * cap) for px, py in stroke])
        x += cw * cap + GAP
    ring_y = BASELINE + cap - DEGREE
    strokes.append(arc(x + DEGREE - GAP * 0.3, ring_y, DEGREE, DEGREE, 180, 540))
    return strokes, cap


def panel_bottom(x):
    return PANEL_Y + BALL / 2


def panel_rows(y_low):
    """Long rows across the panel, from the top down to y_low, ending on the left."""
    ys = [y_low + SWEEP * k for k in range(int((PANEL_RIM - SWEEP / 2 - y_low) / SWEEP) + 1)][::-1]
    path = []
    for i, y in enumerate(ys):
        x1 = math.sqrt(PANEL_RIM ** 2 - y ** 2)
        path += [(x1, y), (-x1, y)] if (len(ys) - i) % 2 else [(-x1, y), (x1, y)]
    return path


def sweep_strip(x_lo, x_hi, top, entry=None):
    """Rows BAND_SWEEP apart across the strip between x_lo and x_hi, over the band the number
    sits in, on the same grid in every strip so the rows line up. With an entry point, the last
    row (the one nearest it) runs in from the strip's left edge and stops there: just one more
    sweep line, so the way in barely shows. Rows below it go first, bottom up, then the rows
    above, top down."""
    bottom = panel_bottom(0)
    ey = bottom + BAND_SWEEP * round((entry[1] - bottom) / BAND_SWEEP) if entry else bottom
    k_lo = math.ceil((bottom - ey) / BAND_SWEEP - 1e-9)
    k_hi = math.floor((top - ey) / BAND_SWEEP + 1e-9)

    def row(k, rightward):
        y = ey + k * BAND_SWEEP
        x1 = min(x_hi, math.sqrt(max(0.0, PANEL_RIM ** 2 - y ** 2)))
        if x1 <= x_lo:
            return None
        return [(x_lo, y), (x1, y)] if rightward else [(x1, y), (x_lo, y)]

    above = [r for r in (row(k, k % 2 == 0) for k in range(k_hi, 0, -1)) if r]  # row 1 ends on the left
    below = [r for r in (row(k, (k - k_lo) % 2 == 0) for k in range(k_lo, 0)) if r]
    if below and above and (below[-1][-1][0] > below[-1][0][0]) != (above[0][0][0] > above[0][-1][0]):
        below = [r[::-1] for r in below]  # end on the side the top row starts
    first = row(0, True) or []
    return [p for r in below + above for p in r] + (first[:1] + [entry] if entry else first)


def panel(value):
    """Sweep the temperature panel smooth and write the number in it. Above the number, long rows.
    Around it, a strip per glyph, each swept just before the glyph is drawn, which also wipes out
    the move into the strip, so nothing joins the glyphs."""
    strokes, cap = temperature(value)
    top = BASELINE + cap + BOLD + 0.07
    edge = math.sqrt(PANEL_RIM ** 2 - PANEL_Y ** 2)
    margin = BALL + BOLD
    x_lo = min(p[0] for p in strokes[0]) - margin
    path = panel_rows(top) + sweep_strip(-edge, x_lo, top)  # the empty part, left of the number
    for i, stroke in enumerate(strokes):
        if i:
            x_lo = max(p[0] for p in strokes[i - 1]) + margin + 0.005
        x_hi = edge if i + 1 == len(strokes) else min(p[0] for p in strokes[i + 1]) - margin
        glyph = best_traversal(stroke, i + 1 == len(strokes))
        path += [(x_lo, path[-1][1])] + sweep_strip(x_lo, x_hi, top, glyph[0]) + bold(glyph)
    return path, cap


# ---------------------------------------------------------------------------------------------
# Scenes

def scene(name):
    """(shapes in drawing order, background passes: [(rows, frame)])."""
    if name == "sunny":
        s = sun((0, -0.42))
        return [s], [(ring_rows(s.c, 0.43, 0.085), Frame())]
    if name == "cloudy":
        sizes = [(0.42, 0.2), (1.0, 0.44)]
        shapes = [cloud((-0.55, -0.14), *sizes[0], 2, 0.6), cloud((0.08, -0.46), *sizes[1])]

        def wind(s, k):  # one long, soft swell, bulging away from the clouds like air flowing past
            y0 = -RIM + 0.0425 + 0.085 * k
            dy = 0.018 * math.sin(2.6 * s + 0.25 * k)
            for c, (w, h) in zip(shapes, sizes):
                q = ((s - c.c[0]) / (w / 2)) ** 2 + ((y0 - c.c[1]) / (h / 1.6)) ** 2
                dy += math.copysign(0.035 * math.exp(-max(0.0, q - 1) * 1.2), y0 - c.c[1])
            return dy
        return shapes, [(parallel_rows(0, 0.085, wind), Frame())]
    if name == "rain":
        # Rain falls below the cloud; above its base, a sky of gentle horizontal lines that flow
        # over and under the cloud. (Near-vertical rain lines would all have to go round the
        # cloud's ends, piling up there.)
        sky = cloud((0, -0.24), 0.85, 0.32)
        base = -0.38
        shapes = [sky, drop((-0.32, -0.7), tip=0.24), drop((0, -0.74), tip=0.24),
                  drop((0.32, -0.7), tip=0.24)]
        return shapes, [(parallel_rows(72, 0.08), Frame(hi=base)),
                        (parallel_rows(0, 0.085, lambda s, k: 0.015 * math.sin(2.4 * s + 0.3 * k)),
                         Frame(lo=base))]
    if name == "snow":
        shapes = [flake((-0.66, -0.22), 0.17, twigs=False), flake((0, -0.43), 0.42),
                  flake((0.66, -0.22), 0.17, twigs=False)]
        # Snow drifting down: wavy vertical lines, which also cross the moves between the flakes.
        return shapes, [(parallel_rows(90, 0.085, lambda s, k: 0.03 * math.sin(5 * s + 0.7 * k)), Frame())]
    if name == "thunderstorm":
        # The bolt hangs just under the cloud. Slanted rows below the cloud's base are the
        # rain; above it, a quiet sky that flows over the cloud. The two stay apart by a
        # hair so the background can pass between them.
        sky = cloud((0.0, -0.20), 0.88, 0.32)
        strike = bolt((0.04, -0.62), scale=0.56)
        base = -0.36
        return [sky, strike], [
            (parallel_rows(70, 0.095), Frame(hi=base)),
            (parallel_rows(0, 0.085, lambda s, k: 0.012 * math.sin(2.3 * s + 0.3 * k)),
             Frame(lo=base)),
        ]
    if name == "partlycloudy":
        # Sun first, cloud second, so the cloud's sweep covers the rays it cuts off.
        cover = cloud((0.26, -0.30), 0.76, 0.30, lobes=3, phase=0.7)
        day = sun_behind((-0.22, -0.42), cover)
        return [day, cover], [(ring_rows(day.c, day.rmax + 0.05, 0.09), Frame())]
    if name == "clear_night":
        moon = crescent((-0.02, -0.42), scale=0.90, tilt=0.65)
        stars = [
            sun((0.50, -0.24), 0.058, 0.10, rays=4, disc=0.028),
            sun((-0.48, -0.58), 0.055, 0.090, rays=4, disc=0.026),
            sun((0.34, -0.70), 0.055, 0.086, rays=4, disc=0.024),
        ]
        return [moon, *stars], [
            (parallel_rows(0, 0.072, lambda s, k: 0.010 * math.sin(2.0 * s + 0.3 * k)), Frame())
        ]
    if name == "fog":
        # Flat wavy banks, stacked, with mist lines flowing around them.
        banks = [
            band((0.04, -0.24), 0.90, 0.15, 2.4, 0.3),
            band((-0.10, -0.46), 0.62, 0.14, 2.8, 1.2),
            band((0.02, -0.68), 0.98, 0.15, 2.2, 2.1),
        ]

        def mist(s, k):
            return 0.026 * math.sin(3.3 * s + 0.55 * k)
        return banks, [(parallel_rows(0, 0.058, mist), Frame())]
    if name == "hail":
        sky = cloud((0, -0.22), 0.82, 0.30)
        stones = [
            pebble((-0.36, -0.58), 0.09),
            pebble((-0.12, -0.70), 0.10),
            pebble((0.14, -0.60), 0.09),
            pebble((0.38, -0.74), 0.08),
        ]
        return [sky, *stones], [
            (parallel_rows(68, 0.10), Frame(hi=-0.36)),
            (parallel_rows(0, 0.09, lambda s, k: 0.01 * math.sin(2.2 * s + 0.3 * k)), Frame(lo=-0.36)),
        ]
    if name == "sleet":
        sky = cloud((0, -0.22), 0.80, 0.30)
        shapes = [
            sky,
            drop((-0.34, -0.62), tip=0.20),
            flake((-0.08, -0.66), 0.16, twigs=False),
            drop((0.20, -0.70), tip=0.18),
            flake((0.42, -0.58), 0.13, twigs=False),
        ]
        return shapes, [
            (parallel_rows(78, 0.09), Frame(hi=-0.36)),
            (parallel_rows(0, 0.09), Frame(lo=-0.36)),
        ]
    if name == "heavy_rain":
        sky = cloud((0, -0.20), 0.90, 0.30)
        drops = [
            drop((x, -0.58 - 0.06 * (i % 2)), tip=0.16)
            for i, x in enumerate((-0.46, -0.23, 0.0, 0.23, 0.46))
        ]
        return [sky, *drops], [
            (parallel_rows(74, 0.07), Frame(hi=-0.34)),
            (parallel_rows(0, 0.09), Frame(lo=-0.34)),
        ]
    if name == "alert":
        sign = warning_sign((0, -0.42), 0.38)
        return [sign], [
            (parallel_rows(0, 0.10, lambda s, k: 0.01 * math.sin(1.6 * s + k)), Frame())
        ]
    raise SystemExit(
        f"unknown condition {name!r}: sunny, partlycloudy, cloudy, fog, rain, "
        "thunderstorm, snow, clear_night or windy"
    )


def _resample(pts):
    sampled = [pts[0]]
    for point in pts[1:]:
        if math.dist(sampled[-1], point) > 1e-9:
            sampled += line(sampled[-1], point)[1:]
    return sampled


def _retrace(pts):
    """Out and back on the same groove: one stroke, drawn twice."""
    pts = _resample(pts)
    return pts + pts[::-1][1:]


def _bow(x0, x1, y, bow):
    """A horizontal stroke bowed up in the middle."""
    n = max(3, int(abs(x1 - x0) / STEP))
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((x0 + (x1 - x0) * t, y + bow * math.sin(math.pi * t)))
    return pts


def _open_curl(tip, radius, turns=1.45, up=True):
    """Open spiral on a rightward tip. About one and a half turns."""
    inner = max(0.018, radius * 0.26)
    if up:
        center = (tip[0], tip[1] + radius)
        angle, spin = -math.pi / 2, 1.0
    else:
        center = (tip[0], tip[1] - radius)
        angle, spin = math.pi / 2, -1.0
    arc = abs(turns) * math.pi * (radius + inner)
    n = max(12, int(arc / STEP))
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append(polar(
            center,
            radius + (inner - radius) * t,
            angle + spin * turns * 2 * math.pi * t,
        ))
    return pts


def _swoosh(x0, x1, y, bow, curl=0.0, up=True):
    body = _bow(x0, x1, y, bow)
    if curl <= 0:
        return body
    return body + _open_curl(body[-1], curl, 1.45, up)[1:]


def _on_rim(y, side):
    """Point on the table edge at height y. side is -1 (left) or +1 (right)."""
    y = max(-RIM + 0.02, min(RIM - 0.02, y))
    return (side * math.sqrt(RIM * RIM - y * y), y)


def _from_edge(path, pts):
    """Draw a stroke that begins on the rim, then come back along it.

    The move from the previous stroke stays on the rim, so nothing vertical or
    diagonal is added inside the picture.
    """
    stroke = _retrace(pts)
    if path:
        path += rim_arc(path[-1], stroke[0])
    path += stroke
    return path


def _gust(side, y, x_end, bow, curl=0.0, curl_up=True, kind="bow"):
    """One wind line. side -1 starts on the left rim; side +1 starts on the right.

    The free end is x_end, so lines that leave the right rim have their left
    tip in the middle of the table. A curl, when there is one, sits on that tip.
    """
    start = _on_rim(y, side)
    if kind == "s":
        body = _s_curve(start[0], x_end, y, bow)
    else:
        body = _bow(start[0], x_end, y, bow)
    if curl <= 0:
        return body
    tip = body[-1]
    hooked = _open_curl(tip, curl, 1.4, up=curl_up)
    if side > 0:
        hooked = [(2 * tip[0] - p[0], p[1]) for p in hooked]
    return body + hooked[1:]


def _wave(x0, x1, y, amp, curl, up):
    """A long S, then a round spiral curl of about one and a quarter turns."""
    body = _s_curve(x0, x1, y, amp)
    return body[:-1] + _open_curl(body[-1], curl, 1.25, up)


def wind_gusts():
    """Four long wavy lines across the area under the temperature.

    They leave the left edge, stay roughly parallel, and each ends in a large
    round curl. The upper curls roll up; the bottom curl rolls down. Nothing
    is drawn at the centre.
    """
    path = []
    # y, wave amplitude, curl radius, curl upward.
    # Curls are about one and a half times the previous size. The lines stay
    # far enough apart that a curl does not meet the wave above or below it.
    rows = (
        (-0.18, 0.05, 0.135, True, 0.02),
        (-0.42, 0.048, 0.12, True, 0.30),
        (-0.64, 0.045, 0.11, True, 0.54),
        (-0.76, 0.038, 0.095, False, 0.10),
    )
    for y, amp, curl, up, x1 in rows:
        start = _on_rim(y, -1)[0]
        room = _on_rim(y, 1)[0] - curl - 0.05
        stroke = _retrace(_wave(start, min(x1, room), y, amp, curl, up))
        # A second trip over the same groove. It adds no new line.
        stroke = stroke + stroke[1:]
        if path:
            path += rim_arc(path[-1], stroke[0])
        path += stroke
    return path


def _draw_from_rim(path, pts):
    """Draw a gust that sits inside the table, starting and ending on the rim.

    The join is the short radial from the point already nearest the edge, so a
    curl that bulges down does not grow a horizontal line out to the rim.
    """
    index = max(range(len(pts)), key=lambda i: math.hypot(*pts[i]))
    outer = pts[index]
    radius = math.hypot(*outer) or 1.0
    rim = (outer[0] / radius * RIM, outer[1] / radius * RIM)
    stroke = _resample(
        [rim]
        + pts[index:]
        + pts[::-1][1:]
        + pts[: index + 1][1:]
        + [rim]
    )
    if path:
        path += rim_arc(path[-1], stroke[0])
    path += stroke
    return path


def _side_gusts():
    """Three wavy gusts on the right of a combined picture. No divider."""
    path = []
    # Top rolls up, middle rolls down, bottom curl is smaller. Radii are about
    # one and a half times the earlier curls. Each tip sits as far right as the
    # spiral can go without leaving the sand or meeting the line beside it.
    rows = (
        (-0.18, 0.040, 0.13, True),
        (-0.42, 0.034, 0.12, False),
        (-0.76, 0.028, 0.08, False),
    )
    limit = 0.942
    left = 0.06
    for y, amp, curl, up in rows:
        lo, hi = left + 0.08, 0.92
        for _ in range(28):
            mid = (lo + hi) / 2
            spiral = _open_curl((mid, y), curl, 1.25, up)
            if max(math.hypot(*p) for p in spiral) <= limit:
                lo = mid
            else:
                hi = mid
        path = _draw_from_rim(path, _wave(left, lo, y, amp, curl, up))
    return path



def _draw_shapes(shapes, leave=None):
    """Sweep and outline shapes, with no full-table background. Links end inside the next shape."""
    path = []
    for index, shape in enumerate(shapes):
        if index + 1 < len(shapes):
            nxt = shapes[index + 1].c
        elif leave is not None:
            nxt = leave
        else:
            nxt = (shape.c[0] + 0.3, shape.c[1])
        if path:
            path += line(path[-1], shape.c)[1:]
        path += shape.draw(nxt)
    return path


def _park(y, reach):
    """Center whose left edge, `reach` out, sits on the table rim."""
    room = max(1e-4, RIM * RIM - y * y)
    return -math.sqrt(room) + reach


def _sunny_emblem():
    """A sun on the left. The way out to the rim continues one ray, so it does not cut the others."""
    center = (-0.40, -0.48)
    rays = 12
    day = sun(center, r_in=0.11, r_out=0.28, rays=rays, disc=0.10)

    def snap_tip(phi):
        return round(phi * rays / (2 * math.pi)) * 2 * math.pi / rays

    day.snap = snap_tip
    outward = math.atan2(center[1], center[0])
    path = day.draw((center[0] + math.cos(outward), center[1] + math.sin(outward)))
    tip = path[-1]
    dx, dy = tip[0] - center[0], tip[1] - center[1]
    span = dx * dx + dy * dy
    if span < 1e-8:
        return path
    # The ray from the sun's centre through the tip, continued to the table edge.
    beam = 2 * (center[0] * dx + center[1] * dy)
    rest = center[0] * center[0] + center[1] * center[1] - RIM * RIM
    root = math.sqrt(max(0.0, beam * beam - 4 * span * rest))
    reach = max((-beam + root) / (2 * span), (-beam - root) / (2 * span))
    if reach > 1.02:
        path += line(tip, (center[0] + reach * dx, center[1] + reach * dy))[1:]
    return path


def _emblem(name):
    """The day's symbol on the left. The path ends on the left rim, so gusts join along the edge."""
    if name == "sunny":
        return _sunny_emblem()
    if name == "hot":
        bulb_r, bulb_y = 0.15, -0.56
        return _thermometer(
            _park(bulb_y, bulb_r), bulb_y, bulb_r, column_top=-0.16, heat=True, finish="left"
        )
    if name == "cold":
        bulb_r, bulb_y = 0.14, -0.58
        return _thermometer(
            _park(bulb_y, bulb_r), bulb_y, bulb_r, column_top=-0.46, spark=0.09, finish="left"
        )
    if name == "alert":
        radius = 0.28
        ang = math.radians(210)  # the left corner
        cy = -0.50
        vy = radius * math.sin(ang)
        cx = _park(cy + vy, 0) - radius * math.cos(ang)
        sign = warning_sign((cx, cy), radius)
        drawn = sign.draw(polar((cx, cy), 1, ang))
        return drawn + drawn[::-1][1:] + drawn[1:]

    if name == "rain":
        cy, reach, w, h = -0.30, 0.26, 0.52, 0.20
        cx = _park(cy, reach)
        sky = cloud((cx, cy), w, h)
        shapes = [
            drop((cx + 0.00, cy - 0.14), tip=0.16),
            drop((cx + 0.14, cy - 0.18), tip=0.16),
            drop((cx + 0.26, cy - 0.12), tip=0.14),
            sky,
        ]
    elif name == "heavy_rain":
        cy, reach = -0.28, 0.28
        cx = _park(cy, reach)
        sky = cloud((cx, cy), 0.56, 0.20)
        shapes = [
            drop((cx + dx, cy - 0.22 - 0.04 * (i % 2)), tip=0.14)
            for i, dx in enumerate((0.00, 0.14, 0.28, 0.40))
        ] + [sky]
    elif name == "thunderstorm":
        cy, reach = -0.26, 0.28
        cx = _park(cy, reach)
        shapes = [bolt((cx + 0.01, cy - 0.05), scale=0.34), cloud((cx, cy), 0.56, 0.20)]
    elif name == "hail":
        cy, reach = -0.28, 0.25
        cx = _park(cy, reach)
        shapes = [
            pebble((cx + 0.02, cy - 0.20), 0.07),
            pebble((cx + 0.16, cy - 0.28), 0.08),
            pebble((cx + 0.30, cy - 0.18), 0.07),
            cloud((cx, cy), 0.50, 0.18),
        ]
    elif name == "sleet":
        cy, reach = -0.28, 0.25
        cx = _park(cy, reach)
        shapes = [
            drop((cx + 0.02, cy - 0.22), tip=0.14),
            flake((cx + 0.16, cy - 0.28), 0.11, twigs=False),
            drop((cx + 0.30, cy - 0.20), tip=0.13),
            cloud((cx, cy), 0.50, 0.18),
        ]
    elif name == "snow":
        cy, reach = -0.42, 0.32
        cx = _park(cy, reach)
        shapes = [
            flake((cx + 0.22, cy + 0.20), 0.10, twigs=False),
            flake((cx, cy), 0.28),
        ]
    elif name == "fog":
        cy, reach = -0.36, 0.32
        cx = _park(cy, reach)
        shapes = [
            band((cx + 0.06, cy + 0.18), 0.50, 0.13, 2.2, 0.4),
            band((cx, cy), 0.56, 0.14, 2.4, 1.1),
        ]
    else:
        cy, reach = -0.36, 0.24
        cx = _park(cy, reach)
        shapes = [cloud((cx, cy), 0.48, 0.18)]
    return _draw_shapes(shapes, leave=(shapes[-1].c[0] - 1.5, shapes[-1].c[1]))


def combined_picture(base):
    """Symbol on the left, gusts on the right, joined only along the table edge."""
    symbol = _emblem(base)
    gusts = _side_gusts()
    if not symbol:
        return gusts
    end = symbol[-1]
    radius = math.hypot(*end) or 1.0
    if abs(radius - RIM) > 0.004:
        rim = (end[0] / radius * RIM, end[1] / radius * RIM)
        symbol = symbol + line(end, rim)[1:]
        end = rim
    return symbol + rim_arc(end, gusts[0]) + gusts


def _quarter(center, radius, a0, a1):
    delta = a1 - a0
    n = max(3, int(abs(delta) * radius / STEP))
    return [polar(center, radius, a0 + delta * i / n) for i in range(n + 1)]


def _arc(center, radius, a0, delta):
    n = max(2, int(abs(delta) * max(radius, 0.02) / STEP))
    return [polar(center, radius, a0 + delta * i / n) for i in range(n + 1)]


def _rising_wave(x, y0, height, amp):
    """One short heat line: a single gentle wave, back on the glass at the top."""
    n = max(8, int(height / STEP))
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((x + amp * math.sin(2 * math.pi * t), y0 + height * t))
    return pts


def _wall_waves(path, x, y_from, y_to, bases, height, amp):
    """Walk the glass wall, drawing each heat line and coming back along it."""
    direction = 1 if y_to >= y_from else -1
    ordered = sorted(bases, reverse=direction < 0)
    for base in ordered:
        if (base - y_from) * direction < -1e-6 or (base - y_to) * direction > 1e-6:
            continue
        path += line(path[-1], (x, base))[1:]
        wave = _rising_wave(x, base, height, amp)
        path += wave[1:] + wave[::-1][1:]
    path += line(path[-1], (x, y_to))[1:]
    return path


def _thermometer(cx, bulb_y, bulb_r, column_top, *, heat=False, spark=0.0, finish="rim"):
    """One thermometer: round bulb, rounded tube, mercury column.

    Heat adds three short rising waves on each side. A snowflake, when asked
    for, sits against the bulb. `finish` "rim" ends on the bottom edge of the
    table; "right" ends on the right of the symbol so a gust can leave it.
    """
    half = max(0.042, bulb_r * 0.28)
    neck = bulb_y + bulb_r
    # A tall glass leaves room for three short heat lines that do not touch.
    rise = 0.50 if bulb_r >= 0.2 else 0.36
    top = min(-0.02, neck + rise)
    wall_lo = neck + half
    if top < wall_lo + 0.08:
        top = wall_lo + 0.08
    center = (cx, bulb_y)
    column_top = max(wall_lo + 0.02, min(top - 0.04, column_top))

    # Sweep the bulb twice. The second pass is the same groove, and it ends
    # on the top of the glass so the mercury can start there.
    drawn = pebble(center, bulb_r).draw((cx, neck + 1))
    path = drawn + drawn[::-1][1:] + drawn[1:]
    path += _retrace([(cx, neck), (cx, column_top)])[1:]

    # Glass, drawn twice on the same groove. Waves are added on the second pass.
    path += _quarter((cx - half, neck), half, 0, math.pi / 2)[1:]
    path += line(path[-1], (cx - half, top))[1:]
    cap = [polar((cx, top), half, math.pi - math.pi * i / 16) for i in range(17)]
    path += cap[1:]
    path += line(path[-1], (cx + half, wall_lo))[1:]
    path += _quarter((cx + half, neck), half, math.pi / 2, math.pi)[1:]

    # Back up the right side, across the cap, and down the left side.
    path += _quarter((cx + half, neck), half, math.pi, math.pi / 2)[1:]
    if heat:
        span = top - wall_lo
        height = min(0.10, max(0.065, span / 5.2))
        gap = (span - 3 * height) / 4
        bases = [wall_lo + gap + i * (height + gap) for i in range(3)]
        amp = 0.028
        path = _wall_waves(path, cx + half, wall_lo, top, bases, height, amp)
        path += cap[::-1][1:]
        path = _wall_waves(path, cx - half, top, wall_lo, bases, height, -amp)
    else:
        path += line(path[-1], (cx + half, top))[1:]
        path += cap[::-1][1:]
        path += line(path[-1], (cx - half, wall_lo))[1:]
    path += _quarter((cx - half, neck), half, math.pi / 2, 0)[1:]

    if spark > 0:
        arm = 0.9 * spark
        # Upper-right of the bulb, close enough that the arm tip meets the glass.
        theta = 0.55
        flake_c = polar(center, bulb_r + arm, theta)
        path += _arc(center, bulb_r, math.pi / 2, theta - math.pi / 2)[1:]
        path += line(path[-1], flake_c)[1:]
        path += flake(flake_c, spark, tilt=theta + math.pi, twigs=False).draw(
            (flake_c[0] + spark, flake_c[1]) if finish == "right" else center
        )
        if finish == "rim":
            # Back on the bulb, then around the left of the glass to the table edge.
            path += line(path[-1], polar(center, bulb_r, theta))[1:]
            path += _arc(center, bulb_r, theta, math.pi / 2 - theta)[1:]
            path += _arc(center, bulb_r, math.pi / 2, math.pi)[1:]
        elif finish == "left":
            path += line(path[-1], polar(center, bulb_r, theta))[1:]
            path += _arc(center, bulb_r, theta, math.pi - theta)[1:]
    elif finish == "rim":
        path += _arc(center, bulb_r, math.pi / 2, math.pi)[1:]
    elif finish == "left":
        path += _arc(center, bulb_r, math.pi / 2, math.pi / 2)[1:]

    if finish == "right" and spark <= 0:
        # Stop on the right shoulder. The return fillet above already ended at the neck;
        # step back out to the right wall so the leaving gust does not cross the tube.
        path += _quarter((cx + half, neck), half, math.pi, math.pi / 2)[1:]
    return path


def hot_picture():
    """A centered thermometer, column near the top, three heat lines on each side."""
    # The bulb sits on the bottom rim so the path can leave along the table edge.
    bulb_r = 0.24
    return _thermometer(0.0, -RIM + bulb_r, bulb_r, column_top=-0.08, heat=True, finish="rim")


def cold_picture():
    """The same glass with the column low, and one small flake beside the bulb."""
    bulb_r = 0.24
    return _thermometer(
        0.0, -RIM + bulb_r, bulb_r, column_top=-0.22, spark=0.11, finish="rim"
    )


def build(condition, value):
    if condition == "windy":
        path = wind_gusts()
    elif condition == "hot":
        path = hot_picture()
    elif condition == "cold":
        path = cold_picture()
    elif isinstance(condition, str) and condition.endswith("_wind"):
        path = combined_picture(condition[: -len("_wind")])
    else:
        path = None
    if path is not None:
        text, cap = panel(value)
        return path + rim_arc(path[-1], text[0]) + text, cap
    shapes, passes = scene(condition)
    rows = passes[0][0]
    path = []
    for i, s in enumerate(shapes):
        nxt = shapes[i + 1].c if i + 1 < len(shapes) else rows[0][0][0]
        if path:
            path += transit(path[-1], s.c, rows)
        path += s.draw(nxt)
    row, closed = rows[0]
    if not closed:
        path += out_to_rim(path[-1], row)
    for rows, frame in passes:
        path = background(path, rows, shapes, frame)
    text, cap = panel(value)
    return path + rim_arc(path[-1], text[0]) + text, cap


def transit(a, b, rows):
    """A move between shapes that the background will wipe out: square across the rows onto the
    nearest one, along it (the row is drawn right over it later), then square across again."""
    row, closed = rows[0]
    if closed:
        return line(a, b)[1:]
    d = (row[-1][0] - row[0][0], row[-1][1] - row[0][1])
    n = (-d[1] / math.hypot(*d), d[0] / math.hypot(*d))
    across = lambda p: p[0] * n[0] + p[1] * n[1]
    mid = (across(a) + across(b)) / 2
    t = min((across(r[len(r) // 2]) for r, _ in rows), key=lambda o: abs(o - mid))
    a1 = (a[0] + (t - across(a)) * n[0], a[1] + (t - across(a)) * n[1])
    b1 = (b[0] + (t - across(b)) * n[0], b[1] + (t - across(b)) * n[1])
    return line(a, a1)[1:] + line(a1, b1)[1:] + line(b1, b)[1:]


def out_to_rim(a, row):
    """From the last shape straight out to the rim, square to the background rows (so they wipe
    the move out) and toward the side where the first row is."""
    d = (row[-1][0] - row[0][0], row[-1][1] - row[0][1])
    n = math.hypot(*d)
    normal = (-d[1] / n, d[0] / n)
    mid = row[len(row) // 2]
    sign = 1 if mid[0] * normal[0] + mid[1] * normal[1] > 0 else -1
    u = (sign * normal[0], sign * normal[1])
    b = a[0] * u[0] + a[1] * u[1]                     # solve |a + t u| = RIM for t > 0
    t = -b + math.sqrt(b * b - (a[0] ** 2 + a[1] ** 2 - RIM ** 2))
    return line(a, (a[0] + t * u[0], a[1] + t * u[1]))[1:]


# ---------------------------------------------------------------------------------------------

def densify(path):
    out = [path[0]]
    for p in path[1:]:
        if math.dist(out[-1], p) > 1e-6:
            out += line(out[-1], p)[1:]
    return out


def write(path, out, rotate, name):
    a = math.radians(rotate)
    pts = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in path]
    with open(out, "w") as f:
        if out.endswith(".json"):
            json.dump({"name": name, "xy": [[round(x, 4), round(y, 4)] for x, y in pts]}, f)
        else:
            for x, y in pts:
                theta = round(math.degrees(math.atan2(y, x)) * 1000) % 360000
                f.write(f"{theta},{round(min(1.0, math.hypot(x, y)) * 100000)}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec", nargs="+", help="CONDITION TEMPERATURE [OUT], or TEMPERATURE [OUT] with --update")
    ap.add_argument("--update", action="store_true", help="redraw only the temperature")
    ap.add_argument("--rotate", type=float, default=0, help="turn the picture counter-clockwise (degrees)")
    args = ap.parse_args()
    spec = args.spec if args.update else args.spec[1:]
    args.condition = None if args.update else args.spec[0]
    args.temperature, args.out = int(spec[0]), (spec[1] if len(spec) > 1 else None)
    if not -99 <= args.temperature <= 199:
        raise SystemExit("temperature must be -99..199")
    if args.update:
        path, cap = panel(args.temperature)
        name = f"weather-temp-{args.temperature}"
    else:
        path, cap = build(args.condition, args.temperature)
        name = f"weather-{args.condition}-{args.temperature}"
    path = densify(path)
    out = args.out or f"{name}.txt"
    write(path, out, args.rotate, name)
    length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
    print(f"{out}: {len(path)} points, {length:.1f} radii, about {length / 0.115 / 60:.1f} min to draw"
          f" (digits {cap:.2f} tall)")
