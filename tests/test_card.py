"""The dashboard card stays on theme tokens and does not invent a default skin."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "custom_components" / "homedics_drift" / "www" / "drift-table-card.js"


def test_card_uses_theme_variables_and_optional_styles() -> None:
    text = CARD.read_text(encoding="utf-8")
    for token in (
        "--primary-text-color",
        "--primary-color",
        "--ha-card-border-radius",
        "--divider-color",
        "--secondary-background-color",
    ):
        assert token in text
    assert 'style === "frosted"' in text or 'style === "frosted"' in text
    assert "frosted" in text and "minimal" in text
    assert "native" in text
    for flag in ("show_now", "show_gallery", "show_create", "show_storage", "show_clean"):
        assert flag in text
    assert "path_known" in text
    assert "requestAnimationFrame" in text
    assert "could not find the Drift player" in text
    assert "resolveDriftEntities" in text
    for piece in (
        "ha-icon-button",
        "ha-control-slider",
        "ha-slider",
        "ha-switch",
        "ha-select",
        "ha-textfield",
        "ha-button",
        "ha-expansion-panel",
        "hass-more-info",
        "localStorage",
        "Stop After",
        "More Colors",
    ):
        assert piece in text
    assert 'type="color"' not in text
    assert "entity_id" in text and "device_id" in text


def test_card_resolves_entities_without_unique_id() -> None:
    """Frontend registry entries omit unique_id. The matcher must still bind."""
    subprocess.run(["node", "tests/test_card_resolve.mjs"], cwd=ROOT, check=True)
    subprocess.run(["node", "tests/test_card_sections.mjs"], cwd=ROOT, check=True)
