"""Path conversion and built-in curves. No model and no Home Assistant."""

from __future__ import annotations

import math

import pytest

from custom_components.homedics_drift.drawing import (
    UploadTicks,
    agents_from_conversation_entities,
    agents_from_info_payload,
    choose_drawing_assistant,
    clean_before_ai_drawing,
    conversation_dropdown,
    feedback_text,
    list_conversation_agents,
    generated_thr,
    generate_points,
    model_text,
    parse_model_points,
    path_from_model,
    xy_to_thr,
)
from custom_components.homedics_drift.patterns import PatternRejected, parse_thr, reusable_id, thr_to_wire


def _ends(text: str) -> tuple[float, float]:
    points = parse_thr(text)
    return points[0][1], points[-1][1]


def test_ai_task_is_always_named_when_options_are_empty() -> None:
    tasks = [
        ("ai_task.openai", "unavailable"),
        ("ai_task.google", "idle"),
    ]
    agents = [
        ("conversation.home_assistant", "Home Assistant"),
        ("conversation.openai", "OpenAI"),
    ]
    assert choose_drawing_assistant(
        configured_task=None,
        configured_agent=None,
        preferred_task="ai_task.google",
        task_states=tasks,
        agents=agents,
    ) == ("ai_task", "ai_task.google")
    assert choose_drawing_assistant(
        configured_task=None,
        configured_agent=None,
        preferred_task=None,
        task_states=tasks,
        agents=agents,
    ) == ("ai_task", "ai_task.google")
    assert choose_drawing_assistant(
        configured_task="ai_task.custom",
        configured_agent=None,
        preferred_task="ai_task.google",
        task_states=tasks,
        agents=agents,
    ) == ("ai_task", "ai_task.custom")
    assert choose_drawing_assistant(
        configured_task=None,
        configured_agent=None,
        preferred_task="ai_task.openai",
        task_states=tasks,
        agents=agents,
    ) == ("ai_task", "ai_task.google")
    assert choose_drawing_assistant(
        configured_task=None,
        configured_agent=None,
        preferred_task="ai_task.openai",
        task_states=[("ai_task.openai", "unavailable")],
        agents=agents,
    ) == ("conversation", "conversation.openai")
    with pytest.raises(PatternRejected, match="No AI Task is available"):
        choose_drawing_assistant(
            configured_task=None,
            configured_agent="conversation.home_assistant",
            preferred_task=None,
            task_states=[],
            agents=[("conversation.home_assistant", "Home Assistant")],
        )


class _AgentInfo:
    """The 2026.11 shape: one object, and iterating it is a TypeError."""

    def __init__(self, agent_id: str, name: str) -> None:
        self.id = agent_id
        self.name = name

    def __iter__(self):
        raise TypeError("'AgentInfo' object is not iterable")


class _State:
    def __init__(self, name: str, state: str = "idle") -> None:
        self.name = name
        self.state = state


class _States:
    def __init__(self, items: dict[str, _State]) -> None:
        self._items = items

    def async_entity_ids(self, domain: str) -> list[str]:
        return [entity_id for entity_id in self._items if entity_id.startswith(f"{domain}.")]

    def get(self, entity_id: str) -> _State | None:
        return self._items.get(entity_id)


class _Hass:
    def __init__(self, items: dict[str, _State]) -> None:
        self.states = _States(items)


def test_agent_info_is_accepted_as_one_object_or_a_list() -> None:
    single = _AgentInfo("conversation.openai", "OpenAI")
    with pytest.raises(TypeError, match="not iterable"):
        list(single)
    assert agents_from_info_payload(single) == [("conversation.openai", "OpenAI")]
    assert agents_from_info_payload(
        [
            _AgentInfo("conversation.home_assistant", "Home Assistant"),
            _AgentInfo("conversation.openai", "OpenAI"),
        ]
    ) == [
        ("conversation.home_assistant", "Home Assistant"),
        ("conversation.openai", "OpenAI"),
    ]
    assert agents_from_info_payload(None) == []
    assert agents_from_info_payload({"id": "conversation.google", "name": "Google"}) == [
        ("conversation.google", "Google")
    ]


def test_conversation_entities_replace_the_agent_info_api() -> None:
    found = agents_from_conversation_entities(
        states=[
            ("conversation.openai", "My OpenAI", "idle"),
            ("light.lamp", "Lamp", "on"),
        ],
        registry=[
            ("conversation.openai", "Other", "Original"),
            ("conversation.google", None, "Google"),
            ("ai_task.openai", "Task", None),
        ],
    )
    assert found == [
        ("conversation.google", "Google"),
        ("conversation.openai", "My OpenAI"),
    ]
    hass = _Hass(
        {
            "conversation.home_assistant": _State("Home Assistant"),
            "conversation.openai": _State("OpenAI"),
            "light.lamp": _State("Lamp"),
        }
    )
    assert list_conversation_agents(hass) == [
        ("conversation.home_assistant", "Home Assistant"),
        ("conversation.openai", "OpenAI"),
    ]
    assert conversation_dropdown(hass) == [
        {"value": "conversation.openai", "label": "OpenAI — conversation.openai"}
    ]

    class _Broken:
        @property
        def states(self) -> object:
            raise RuntimeError("state machine down")

    assert conversation_dropdown(_Broken()) == []
    assert list_conversation_agents(_Broken()) == []


def test_ai_drawings_clean_first_only_while_power_is_on() -> None:
    assert clean_before_ai_drawing(None, play=True, power_on=True) is True
    assert clean_before_ai_drawing(True, play=True, power_on=True) is True
    assert clean_before_ai_drawing(False, play=True, power_on=True) is False
    assert clean_before_ai_drawing(True, play=True, power_on=False) is False
    assert clean_before_ai_drawing(True, play=False, power_on=True) is False
    assert feedback_text("cleaning") == "Cleaning sand…"


def test_upload_feedback_steps_about_every_ten_percent() -> None:
    ticks = UploadTicks()
    notes: list[int] = []
    for done in range(1, 11):
        notes.extend(ticks.crossed(done, 10))
    assert notes == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert feedback_text("drawing", prompt="a star", assistant="OpenAI") == (
        'Drawing "a star" with OpenAI…'
    )
    assert feedback_text("uploading", percent=20) == "Uploading to table… 20%"
    assert feedback_text("done", name="Lotus Mandala", playing=True) == (
        "Done: Lotus Mandala saved and playing"
    )
    assert feedback_text("done", name="Lotus Mandala") == "Done: Lotus Mandala saved"
    assert feedback_text("busy") == "A drawing is already in progress."
    assert feedback_text("error", error="The table rejected the upload") == (
        "The table rejected the upload"
    )


def test_model_json_becomes_a_valid_centre_to_rim_path() -> None:
    text = path_from_model('Here you go:\n```json\n[[0.2, 0.2], [0.6, -0.1], [0.3, 0.4]]\n```')
    start, end = _ends(text)
    assert start == 0
    assert end == 1
    wire = thr_to_wire(text)
    assert wire[0][1] == 0
    assert wire[-1][1] == 50000
    assert len(wire) >= 2


def test_bad_model_output_is_rejected_without_a_second_guess() -> None:
    with pytest.raises(PatternRejected, match="did not return a list"):
        parse_model_points("I cannot draw that")
    with pytest.raises(PatternRejected, match="at least two points"):
        xy_to_thr([(0.2, 0.2)])
    assert model_text(
        {"response": {"speech": {"plain": {"speech": "[[0, 0], [1, 0]]"}}}}
    ) == "[[0, 0], [1, 0]]"
    assert model_text({"data": {"path": "[[0, 0], [0.5, 0.5]]"}}) == "[[0, 0], [0.5, 0.5]]"


def test_simple_svg_path_is_accepted() -> None:
    points = parse_model_points("M 0 0 L 0.5 0.2 L 0.2 -0.4")
    assert points[0] == (0, 0)
    assert points[-1] == (0.2, -0.4)
    text = path_from_model("M 0 0 L 0.4 0.2")
    assert _ends(text) == (0, 1)


def test_builtin_curves_need_no_model_and_stay_valid() -> None:
    for kind, params in (
        ("spiral", {"turns": 3}),
        ("rose", {"petals": 5}),
        ("star", {"points": 5}),
        ("wave", {"waves": 4}),
        ("spirograph", {"outer": 5, "inner": 3, "pen": 2, "loops": 2}),
    ):
        text = generated_thr(kind, params)
        start, end = _ends(text)
        assert start == 0
        assert end == 1
        assert thr_to_wire(text)
    assert len(generate_points("star", {"points": 5})) >= 6
    with pytest.raises(PatternRejected, match="type must be"):
        generate_points("logo")
    with pytest.raises(PatternRejected, match="inner must be smaller"):
        generate_points("spirograph", {"outer": 3, "inner": 4, "pen": 1, "loops": 1})


def test_a_large_jump_is_filled_and_the_clean_id_stays_protected() -> None:
    text = xy_to_thr([(0.0, 0.0), (0.9, 0.0)])
    points = parse_thr(text)
    for first, second in zip(points, points[1:]):
        gap = math.hypot(second[1] - first[1], (second[0] - first[0]) * max(second[1], first[1]))
        assert gap < 0.25
    assert reusable_id(50000, {50000}) is None
    assert reusable_id(50010, {50000}) == 50010
