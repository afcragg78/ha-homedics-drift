"""Import the packet codec without loading the Home Assistant integration."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "homedics_drift"

if "custom_components.homedics_drift" not in sys.modules:
    parent = sys.modules.get("custom_components")
    if parent is None:
        parent = types.ModuleType("custom_components")
        parent.__path__ = [str(ROOT / "custom_components")]  # type: ignore[attr-defined]
        sys.modules["custom_components"] = parent
    package = types.ModuleType("custom_components.homedics_drift")
    package.__path__ = [str(INTEGRATION)]  # type: ignore[attr-defined]
    package.__package__ = "custom_components.homedics_drift"
    sys.modules["custom_components.homedics_drift"] = package
