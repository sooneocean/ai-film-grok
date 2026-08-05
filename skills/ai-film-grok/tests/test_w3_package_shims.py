"""W3 · package dirs + top-level shims keep hard-compat imports."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_assets_package_and_shim_identity() -> None:
    import assets.visual_bible as pkg
    import visual_bible as shim

    assert shim is pkg
    assert hasattr(shim, "load_bible")


def test_spine_package_and_shim_identity() -> None:
    import dispatch as shim
    import spine.dispatch as pkg

    assert shim is pkg
    assert hasattr(shim, "build_dispatch")


def test_gates_and_plan_shims() -> None:
    import preflight as pre_shim
    import gates.preflight as pre_pkg
    import beat_spine as bs_shim
    import plan.beat_spine as bs_pkg

    assert pre_shim is pre_pkg
    assert bs_shim is bs_pkg


def test_shim_modules_are_thin() -> None:
    for name in ("visual_bible.py", "dispatch.py", "next_actions.py", "preflight.py", "beat_spine.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "_sys.modules[__name__]" in text or "sys.modules[__name__]" in text
        assert len(text.splitlines()) < 30
