"""Manifest checks that must stay compatible with Home Assistant Bluetooth.

Core rejects a ``local_name`` matcher whose first three characters contain
``*`` or ``[`` and refuses to set up Bluetooth at all, which takes every
Bluetooth integration down with it.
"""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "homedics_drift"
    / "manifest.json"
)
# Same rule as homeassistant.components.bluetooth.match._local_name_to_index_key.
_PATTERN_CHARS = frozenset("*?[")
_LITERAL_PREFIX = 3


def test_local_name_matchers_have_no_pattern_in_the_first_three_characters() -> None:
    manifest = json.loads(MANIFEST.read_text())
    for matcher in manifest.get("bluetooth", []):
        local_name = matcher.get("local_name")
        if not isinstance(local_name, str):
            continue
        prefix = local_name[:_LITERAL_PREFIX]
        assert not any(char in _PATTERN_CHARS for char in prefix), (
            "local_name matchers may not have a wildcard in the first "
            f"{_LITERAL_PREFIX} characters ({local_name})"
        )


def test_manifest_does_not_use_the_rejected_ks_wildcard() -> None:
    text = MANIFEST.read_text()
    assert "KS*" not in text
    assert "local_name" not in json.loads(text)
