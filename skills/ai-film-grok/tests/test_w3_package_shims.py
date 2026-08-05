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


def test_w7_cli_package_and_shim_identity() -> None:
    """W7 · cli_*.py live under scripts/cli/ with thin top-level shims."""
    import cli.cli_post as pkg
    import cli_post as shim
    import cli.cli_media as media_pkg
    import cli_media as media_shim

    assert shim is pkg
    assert media_shim is media_pkg
    assert (SCRIPTS / "cli" / "cli_post.py").is_file()
    text = (SCRIPTS / "cli_post.py").read_text(encoding="utf-8")
    assert "sys.modules[__name__]" in text or "_sys.modules[__name__]" in text
    assert len(text.splitlines()) < 30
