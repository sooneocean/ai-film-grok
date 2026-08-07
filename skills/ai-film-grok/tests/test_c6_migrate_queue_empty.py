"""C6.1 honesty: safe migrate queue for thick top-level is intentionally empty.

Non-shim top-level residuals are hubs/orchestrators (not vanity package moves).
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# IRON keep top-level (see docs/reports/2026-08-06-code-metabolism-inventory.md)
INTENTIONAL_RESIDUAL = frozenset(
    {
        "aifilm_grok.py",  # CLI hub
        "workflow_pack.py",  # ship-prep thrash surface
        "smoke_console.py",  # live harness entry
        "web_api.py",
        "web_core.py",
        "asset_picker.py",
        "gate_panel.py",
        "onboarding.py",
        "onboarding_planner.py",  # onboarding v2 auto-decompose (console entry)
        "composition_fill_gate.py",  # thick gate leaf; peel only bug-driven
    }
)


def _is_shim(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) <= 15 and "def " not in text and "class " not in text:
        return True
    if re.search(r"from \S+ import \w+ as _impl|hard-compat|shim", text, re.I):
        if text.count("\n") < 50 and text.count("def ") <= 2:
            return True
    return False


def test_non_shim_top_level_only_intentional_residuals() -> None:
    unexpected: list[str] = []
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _is_shim(text):
            continue
        if path.name not in INTENTIONAL_RESIDUAL:
            unexpected.append(path.name)
    assert not unexpected, (
        "new thick top-level modules appeared outside IRON residual set — "
        f"either migrate (C6.1) or document in inventory: {unexpected}"
    )
