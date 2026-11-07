"""The dashboard card stays on theme tokens and does not invent a default skin."""

from __future__ import annotations

from pathlib import Path

CARD = Path(__file__).resolve().parents[1] / "custom_components" / "homedics_drift" / "www" / "drift-table-card.js"


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
