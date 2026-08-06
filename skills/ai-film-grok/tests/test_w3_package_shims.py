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
    import beat_spine as bs_shim
    import gates.preflight as pre_pkg
    import plan.beat_spine as bs_pkg
    import preflight as pre_shim

    assert pre_shim is pre_pkg
    assert bs_shim is bs_pkg


def test_shim_modules_are_thin() -> None:
    for name in (
        "visual_bible.py",
        "dispatch.py",
        "next_actions.py",
        "preflight.py",
        "beat_spine.py",
        "edit_policy_shared.py",
    ):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "_sys.modules[__name__]" in text or "sys.modules[__name__]" in text
        assert len(text.splitlines()) < 30


def test_edit_policy_shared_shim_and_cycle_free_heat() -> None:
    """Shared leaf breaks heat↔policy cycle; shim identity matches package."""
    import edit_policy as policy
    import edit_policy_heat as heat
    import edit_policy_shared as shim
    import narrative.edit_policy_shared as pkg

    assert shim is pkg
    assert heat.PolicyError is policy.PolicyError is pkg.PolicyError
    heat_src = (SCRIPTS / "narrative" / "edit_policy_heat.py").read_text(encoding="utf-8")
    assert "sys.modules.get" not in heat_src.split("HEAT_SCALES")[0]


def test_w7_cli_package_and_shim_identity() -> None:
    """W7 · cli_*.py live under scripts/cli/ with thin top-level shims."""
    import cli.cli_media as media_pkg
    import cli.cli_post as pkg
    import cli_media as media_shim
    import cli_post as shim

    assert shim is pkg
    assert media_shim is media_pkg
    assert (SCRIPTS / "cli" / "cli_post.py").is_file()
    text = (SCRIPTS / "cli_post.py").read_text(encoding="utf-8")
    assert "sys.modules[__name__]" in text or "_sys.modules[__name__]" in text
    assert len(text.splitlines()) < 30


def test_w7_post_package_and_shim_identity() -> None:
    """W7 · post domain modules live under scripts/post/ with thin shims."""
    import compose_render as shim
    import export_composition as exp_shim
    import post.compose_render as pkg
    import post.export_composition as exp_pkg

    assert shim is pkg
    assert exp_shim is exp_pkg
    text = (SCRIPTS / "compose_render.py").read_text(encoding="utf-8")
    assert "sys.modules[__name__]" in text or "_sys.modules[__name__]" in text
    assert len(text.splitlines()) < 30


def test_w7_plan_package_and_shim_identity() -> None:
    """W7 · plan domain modules live under scripts/plan/ with thin shims."""
    import film_spec as shim
    import plan.film_spec as pkg
    import plan.story_plan as sp_pkg
    import story_plan as sp_shim

    assert shim is pkg
    assert sp_shim is sp_pkg
    text = (SCRIPTS / "film_spec.py").read_text(encoding="utf-8")
    assert "sys.modules[__name__]" in text or "_sys.modules[__name__]" in text
    assert len(text.splitlines()) < 30


def test_w7_narrative_package_and_shim_identity() -> None:
    """W7 · narrative domain modules live under scripts/narrative/ with thin shims."""
    import edit_policy as shim
    import heat_check as hc_shim
    import narrative.edit_policy as pkg
    import narrative.heat_check as hc_pkg

    assert shim is pkg
    assert hc_shim is hc_pkg
    text = (SCRIPTS / "edit_policy.py").read_text(encoding="utf-8")
    assert "sys.modules[__name__]" in text or "_sys.modules[__name__]" in text
    assert len(text.splitlines()) < 30
