"""Structural guard: metabolism terminal residual stays intentional.

After P3-1 closeout only two non-shim top-level domain modules remain by policy:
CLI hub ``aifilm_grok`` and thrash orchestrator ``workflow_pack``.

These tests drive real filesystem layout (not hard-coded “we claim freeze”):
they fail if someone vanity-moves the hub or invents a package twin for
workflow_pack without the freeze docs being updated intentionally.
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
# tests/ → skill package → plugin root (docs/reports lives at plugin root)
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
INVENTORY = PLUGIN_ROOT / "docs" / "reports" / "2026-08-06-code-metabolism-inventory.md"


def test_aifilm_grok_hub_stays_top_level_entry() -> None:
    hub = SCRIPTS / "aifilm_grok.py"
    assert hub.is_file(), "CLI hub missing"
    text = hub.read_text(encoding="utf-8")
    # Must be real entry (not a thin package shim)
    assert "sys.modules[__name__]" not in text
    assert "argparse" in text or "def main" in text
    # No package twin that would imply hub was relocated
    for pkg in ("cli", "spine", "plan", "post", "media", "util"):
        assert not (SCRIPTS / pkg / "aifilm_grok.py").is_file()


def test_workflow_pack_stays_top_level_until_bug_driven_peel() -> None:
    pack = SCRIPTS / "workflow_pack.py"
    assert pack.is_file(), "workflow_pack missing"
    text = pack.read_text(encoding="utf-8")
    assert "sys.modules[__name__]" not in text
    assert "def ship_prep" in text or "ship_prep" in text
    # Vanity package twin forbidden while freeze is in force
    for pkg in ("post", "spine", "plan", "cli"):
        assert not (SCRIPTS / pkg / "workflow_pack.py").is_file()


def test_inventory_documents_terminal_freeze() -> None:
    assert INVENTORY.is_file()
    body = INVENTORY.read_text(encoding="utf-8")
    assert "aifilm_grok" in body
    assert "workflow_pack" in body
    assert "Keep top-level" in body or "top-level forever" in body
    assert "bug" in body.lower() and "peel" in body.lower()
