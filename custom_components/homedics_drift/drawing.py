"""Turn a list of points, or a short description of a curve, into a valid .thr path.

The table only accepts one continuous polar path. These helpers resample that
path, keep it inside the disc, start at the centre, and finish on the rim.
No network calls live here.
"""

from __future__ import annotations

import json
import math
import re

from .patterns import PatternRejected, densify, wire_point

_FENCE = re.compile(r"```(?:json|svg)?\s*|```", re.IGNORECASE)


DEFAULT_CONVERSATION_AGENTS = frozenset(
    {"conversation.home_assistant", "homeassistant"}
)
_UNAVAILABLE = "unavailable"


def choose_drawing_assistant(
    *,
    configured_task: str | None,
    configured_agent: str | None,
    preferred_task: str | None,
    task_states: list[tuple[str, str]],
    agents: list[tuple[str, str]],
) -> tuple[str, str]:
    """Pick an explicit AI Task entity or a non-default conversation agent.

    The AI Task service errors if no entity is passed and Home Assistant has
    no preferred one. Order: the entity saved in options, then Home Assistant's
    preferred AI Task, then the first AI Task that is not unavailable, then a
    conversation agent other than the built-in Home Assistant agent.
    """
    saved_task = (configured_task or "").strip() or None
    saved_agent = (configured_agent or "").strip() or None
    if saved_task:
        return ("ai_task", saved_task)

    available = [
        entity_id
        for entity_id, state in task_states
        if entity_id and state != _UNAVAILABLE
    ]
    if preferred_task and preferred_task in available:
        return ("ai_task", preferred_task)
    if available:
        return ("ai_task", sorted(available)[0])

    extra_agents = [
        agent_id
        for agent_id, _name in agents
        if agent_id and agent_id not in DEFAULT_CONVERSATION_AGENTS
    ]
    if saved_agent and saved_agent not in DEFAULT_CONVERSATION_AGENTS:
        return ("conversation", saved_agent)
    if extra_agents:
        return ("conversation", extra_agents[0])
    raise PatternRejected(
        "No AI Task is available. Add an AI integration such as OpenAI or Google, "
        "then pick it in this integration's options. The built-in Home Assistant "
        "conversation agent cannot draw a pattern."
    )


class UploadTicks:
    """Percent marks to announce, about every 10 points."""

    def __init__(self) -> None:
        self._last = 0

    def crossed(self, done: int, total: int) -> list[int]:
        if total <= 0 or done <= 0:
            return []
        value = min(100, int(done * 100 / total))
        marks: list[int] = []
        mark = self._last + 10
        while mark <= value:
            marks.append(mark)
            mark += 10
        if marks:
            self._last = marks[-1]
        return marks


def feedback_text(
    stage: str,
    *,
    prompt: str = "",
    assistant: str = "",
    percent: int | None = None,
    name: str = "",
    playing: bool = False,
    error: str = "",
) -> str:
    """The sentence shown for one stage of a drawing or gallery send."""
    if stage == "drawing":
        return f'Drawing "{prompt}" with {assistant}…'
    if stage == "uploading":
        return f"Uploading to table… {percent}%"
    if stage == "done":
        if playing:
            return f"Done: {name} saved and playing"
        return f"Done: {name} saved"
    if stage == "busy":
        return "A drawing is already in progress."
    return error or "The drawing failed"


def build_instructions(prompt: str) -> str:
    """One request for a single path. Callers send this once."""
    subject = " ".join(prompt.split())
    return (
        "Draw one continuous line for a round sand table. "
        f"Subject: {subject}. "
        "Return only a JSON list of [x, y] numbers, each between -1 and 1. "
        "Use between 20 and 80 points. Do not break the line. Do not add words. "
        "Example: [[0, 0], [0.2, 0.4], [0.6, -0.2]]"
    )


def model_text(payload: object) -> str:
    """Pull the path text out of an AI Task or conversation result."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return json.dumps(payload)
    if not isinstance(payload, dict):
        raise PatternRejected("The model did not return a drawing path")
    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return data
    if isinstance(data, list):
        return json.dumps(data)
    if isinstance(data, dict):
        for key in ("path", "points", "coordinates", "polyline", "d"):
            if key in data and data[key] not in (None, ""):
                value = data[key]
                return value if isinstance(value, str) else json.dumps(value)
    speech = _conversation_speech(payload)
    if speech:
        return speech
    if isinstance(data, dict) and data:
        return json.dumps(data)
    raise PatternRejected("The model did not return a drawing path")


def _conversation_speech(payload: dict[str, object]) -> str:
    response = payload.get("response")
    if not isinstance(response, dict):
        return ""
    speech = response.get("speech")
    if isinstance(speech, dict):
        plain = speech.get("plain")
        if isinstance(plain, dict) and isinstance(plain.get("speech"), str):
            return plain["speech"]
        if isinstance(speech.get("speech"), str):
            return str(speech["speech"])
    if isinstance(speech, str):
        return speech
    return ""


def parse_model_points(raw: str) -> list[tuple[float, float]]:
    """Read [x, y] pairs, or a simple SVG path, from model text."""
    text = _FENCE.sub("", raw).strip()
    if not text:
        raise PatternRejected("The model did not return a drawing path")
    parsed = _extract_json(text)
    if parsed is not None:
        return _points_from_json(parsed)
    if re.search(r"(?:^|\s|\"|')[MLCQZmlcqz]\s*-?\d", text) or 'd="' in text:
        svg = _svg_points(text)
        if len(svg) >= 2:
            return svg
    raise PatternRejected("The model did not return a list of [x, y] points")


def _extract_json(text: str) -> object | None:
    start = next((index for index, char in enumerate(text) if char in "[{"), None)
    if start is None:
        return None
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except json.JSONDecodeError:
        return None


def _points_from_json(parsed: object) -> list[tuple[float, float]]:
    if isinstance(parsed, dict):
        for key in ("points", "path", "coordinates", "polyline"):
            if key in parsed:
                return _points_from_json(parsed[key])
        raise PatternRejected("The model did not return a list of [x, y] points")
    if isinstance(parsed, str):
        return parse_model_points(parsed)
    if not isinstance(parsed, list) or not parsed:
        raise PatternRejected("The model did not return a list of [x, y] points")
    points: list[tuple[float, float]] = []
    for item in parsed:
        if isinstance(item, dict) and "x" in item and "y" in item:
            pair = (item["x"], item["y"])
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            pair = (item[0], item[1])
        else:
            raise PatternRejected("The model did not return a list of [x, y] points")
        try:
            x = float(pair[0])
            y = float(pair[1])
        except (TypeError, ValueError) as err:
            raise PatternRejected("The model returned a point that is not a number") from err
        if not math.isfinite(x) or not math.isfinite(y):
            raise PatternRejected("The model returned a point that is not a number")
        points.append((x, y))
    return points


def _svg_points(text: str) -> list[tuple[float, float]]:
    match = re.search(r'd="([^"]+)"', text)
    body = match.group(1) if match else text
    tokens = re.findall(r"[MLCQZmlcqz]|-?\d*\.?\d+(?:e[-+]?\d+)?", body)
    if not tokens:
        return []
    points: list[tuple[float, float]] = []
    command = ""
    numbers: list[float] = []
    cursor = (0.0, 0.0)
    start = (0.0, 0.0)

    def flush() -> None:
        nonlocal cursor, start, command
        if not command:
            return
        needed = {"M": 2, "L": 2, "C": 6, "Q": 4, "Z": 0}[command.upper()]
        relative = command.islower()
        idx = 0
        while command.upper() == "Z" or idx + needed <= len(numbers):
            if command.upper() == "Z":
                points.append(start)
                cursor = start
                return
            chunk = numbers[idx : idx + needed]
            idx += needed
            absolute = []
            for position in range(0, needed, 2):
                px = chunk[position] + (cursor[0] if relative else 0.0)
                py = chunk[position + 1] + (cursor[1] if relative else 0.0)
                absolute.append((px, py))
            if command.upper() == "M":
                cursor = absolute[0]
                start = cursor
                points.append(cursor)
                command = "l" if relative else "L"
            elif command.upper() == "L":
                cursor = absolute[0]
                points.append(cursor)
            elif command.upper() == "Q":
                points.extend(_sample_quadratic(cursor, absolute[0], absolute[1]))
                cursor = absolute[1]
            elif command.upper() == "C":
                points.extend(_sample_cubic(cursor, absolute[0], absolute[1], absolute[2]))
                cursor = absolute[2]
            if command.upper() == "Z":
                return

    for token in tokens:
        if token.isalpha():
            flush()
            command = token
            numbers = []
            continue
        numbers.append(float(token))
    flush()
    return points


def _sample_quadratic(
    start: tuple[float, float], control: tuple[float, float], end: tuple[float, float]
) -> list[tuple[float, float]]:
    return [
        (
            (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t**2 * end[0],
            (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t**2 * end[1],
        )
        for t in (0.25, 0.5, 0.75, 1.0)
    ]


def _sample_cubic(
    start: tuple[float, float],
    control_a: tuple[float, float],
    control_b: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    sampled = []
    for step in range(1, 5):
        t = step / 4
        u = 1 - t
        sampled.append(
            (
                u**3 * start[0]
                + 3 * u**2 * t * control_a[0]
                + 3 * u * t**2 * control_b[0]
                + t**3 * end[0],
                u**3 * start[1]
                + 3 * u**2 * t * control_a[1]
                + 3 * u * t**2 * control_b[1]
                + t**3 * end[1],
            )
        )
    return sampled


def _clamp_disk(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    clamped: list[tuple[float, float]] = []
    for x, y in points:
        radius = math.hypot(x, y)
        if radius > 1:
            x, y = x / radius, y / radius
        clamped.append((x, y))
    return clamped


def _resample(points: list[tuple[float, float]], step: float = 0.03) -> list[tuple[float, float]]:
    if not points:
        return []
    output = [points[0]]
    for point in points[1:]:
        previous = output[-1]
        distance = math.hypot(point[0] - previous[0], point[1] - previous[1])
        pieces = max(1, math.ceil(distance / step - 1e-12))
        for index in range(1, pieces + 1):
            fraction = index / pieces
            output.append(
                (
                    previous[0] + (point[0] - previous[0]) * fraction,
                    previous[1] + (point[1] - previous[1]) * fraction,
                )
            )
    return output


def _smooth(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    smoothed = [points[0]]
    for index in range(1, len(points) - 1):
        smoothed.append(
            (
                (points[index - 1][0] + points[index][0] + points[index + 1][0]) / 3,
                (points[index - 1][1] + points[index][1] + points[index + 1][1]) / 3,
            )
        )
    smoothed.append(points[-1])
    return smoothed


def _radial_line(
    start: tuple[float, float], end: tuple[float, float], step: float = 0.03
) -> list[tuple[float, float]]:
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    pieces = max(1, math.ceil(distance / step - 1e-12))
    return [
        (
            start[0] + (end[0] - start[0]) * index / pieces,
            start[1] + (end[1] - start[1]) * index / pieces,
        )
        for index in range(1, pieces + 1)
    ]


def _connect_large_jumps(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Replace a long jump with a short spiral so the ball does not cut across."""
    if len(points) < 2:
        return points
    output = [points[0]]
    for point in points[1:]:
        previous = output[-1]
        gap = math.hypot(point[0] - previous[0], point[1] - previous[1])
        if gap <= 0.3:
            output.extend(_radial_line(previous, point))
            continue
        start_radius = math.hypot(*previous)
        end_radius = math.hypot(*point)
        start_angle = math.atan2(previous[1], previous[0]) if start_radius > 1e-6 else 0.0
        end_angle = math.atan2(point[1], point[0]) if end_radius > 1e-6 else start_angle
        while end_angle - start_angle > math.pi:
            end_angle -= 2 * math.pi
        while end_angle - start_angle < -math.pi:
            end_angle += 2 * math.pi
        steps = max(4, math.ceil(gap / 0.04))
        for index in range(1, steps + 1):
            fraction = index / steps
            angle = start_angle + (end_angle - start_angle) * fraction
            radius = start_radius + (end_radius - start_radius) * fraction
            output.append((radius * math.cos(angle), radius * math.sin(angle)))
    return output


def prepare_path(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Resample, clamp, smooth, and force a centre start and a rim end."""
    if len(points) < 2:
        raise PatternRejected("The drawing needs at least two points")
    path = _clamp_disk(points)
    path = _resample(path)
    path = _clamp_disk(_smooth(path))
    path = _connect_large_jumps(path)
    if math.hypot(*path[0]) > 0.05:
        path = [(0.0, 0.0), *path]
    end_radius = math.hypot(*path[-1])
    if end_radius < 0.92:
        if end_radius < 1e-6:
            rim = (1.0, 0.0)
        else:
            rim = (path[-1][0] / end_radius, path[-1][1] / end_radius)
        path = [*path, *_radial_line(path[-1], rim)]
    path = _clamp_disk(path)
    path[0] = (0.0, 0.0)
    end_radius = math.hypot(*path[-1])
    if end_radius < 1e-6:
        path[-1] = (1.0, 0.0)
    else:
        path[-1] = (path[-1][0] / end_radius, path[-1][1] / end_radius)
    return path


def xy_to_thr(points: list[tuple[float, float]]) -> str:
    """Convert prepared cartesian points into theta-rho text the uploader accepts."""
    path = prepare_path(points)
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in path:
        radius = min(1.0, math.hypot(x, y))
        theta = math.atan2(y, x)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, radius))
    polar = densify(polar, max_step=0.02)
    if len(polar) < 2:
        raise PatternRejected("The drawing could not be turned into a path")
    polar[0] = (polar[0][0], 0.0)
    polar[-1] = (polar[-1][0], 1.0)
    for theta, rho in polar:
        wire_point(theta, rho)
    lines = [f"{theta:.6f} {min(1.0, max(0.0, rho)):.6f}" for theta, rho in polar]
    return "\n".join(lines) + "\n"


def path_from_model(raw: str) -> str:
    """Validate model output and return thr text, or raise a clear error."""
    return xy_to_thr(parse_model_points(raw))


def _number(params: dict[str, object], key: str, default: float, low: float, high: float) -> float:
    value = params.get(key, default)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise PatternRejected(f"{key} must be a number") from err
    if not math.isfinite(number) or not low <= number <= high:
        raise PatternRejected(f"{key} must be between {low:g} and {high:g}")
    return number


def generate_points(kind: str, params: dict[str, object] | None = None) -> list[tuple[float, float]]:
    """A built-in curve. No model is called."""
    options = params or {}
    name = kind.strip().lower()
    if name == "spiral":
        turns = _number(options, "turns", 8, 1, 40)
        outward = bool(options.get("outward", True))
        total = turns * 2 * math.pi
        steps = int(turns * 120)
        points = []
        for index in range(steps + 1):
            fraction = index / steps
            rho = fraction if outward else 1 - fraction
            theta = total * fraction
            points.append((rho * math.cos(theta), rho * math.sin(theta)))
        return points
    if name == "rose":
        petals = int(_number(options, "petals", 5, 2, 12))
        limit = math.pi if petals % 2 else 2 * math.pi
        points = []
        steps = 480
        for index in range(steps + 1):
            theta = limit * index / steps
            rho = abs(math.cos(petals * theta)) * 0.9
            points.append((rho * math.cos(theta), rho * math.sin(theta)))
        return points
    if name == "star":
        tips = int(_number(options, "points", 5, 3, 12))
        points = []
        for index in range(tips * 2 + 1):
            angle = -math.pi / 2 + index * math.pi / tips
            radius = 0.9 if index % 2 == 0 else 0.38
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
        return points
    if name == "wave":
        waves = _number(options, "waves", 6, 1, 24)
        points = []
        steps = 360
        for index in range(steps + 1):
            x = -0.9 + 1.8 * index / steps
            y = 0.55 * math.sin(waves * math.pi * (x + 0.9) / 1.8)
            points.append((x, y))
        return points
    if name == "spirograph":
        outer = _number(options, "outer", 5, 1, 20)
        inner = _number(options, "inner", 3, 0.2, 19)
        if inner >= outer:
            raise PatternRejected("inner must be smaller than outer")
        offset = _number(options, "pen", 2, 0.1, 20)
        loops = _number(options, "loops", 3, 1, 12)
        steps = int(loops * 500)
        raw = []
        for index in range(steps + 1):
            theta = loops * 2 * math.pi * index / steps
            raw.append(
                (
                    (outer - inner) * math.cos(theta)
                    + offset * math.cos((outer - inner) / inner * theta),
                    (outer - inner) * math.sin(theta)
                    - offset * math.sin((outer - inner) / inner * theta),
                )
            )
        scale = max(math.hypot(x, y) for x, y in raw) or 1.0
        return [(x / scale * 0.85, y / scale * 0.85) for x, y in raw]
    raise PatternRejected("type must be spiral, rose, star, wave, or spirograph")


def generated_thr(kind: str, params: dict[str, object] | None = None) -> str:
    """Theta-rho text for a built-in curve."""
    return xy_to_thr(generate_points(kind, params))
