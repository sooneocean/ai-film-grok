from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dispatch import build_dispatch  # noqa: E402
from dispatch_compact import compact_dispatch  # noqa: E402
from weapon_router import build_weapon_route  # noqa: E402


def _workflow(stage: str) -> dict[str, object]:
    return {"mode": "professional", "current_stage": stage}


def test_visual_demand_auto_selects_verified_local_weapon(tmp_path: Path) -> None:
    route = build_weapon_route(tmp_path, workflow=_workflow("shot_animatic_lock"))

    assert route["status"] == "ready"
    assert route["weapon_id"] == "qwen-image-2512-quality"
    assert route["auto_select"] is True
    assert route["auto_execute_when_requested"] is True
    assert route["requires_live_probe"] is True
    assert route["advance_eligible"] is False


def test_existing_still_provider_lock_wins_over_armory(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"still_provider": "grok"}),
        encoding="utf-8",
    )

    route = build_weapon_route(tmp_path, workflow=_workflow("pilot_approval"))

    assert route["status"] == "provider_locked"
    assert route["provider"] == "grok"
    assert route["auto_select"] is False


def test_non_visual_stage_does_not_route_weapon(tmp_path: Path) -> None:
    route = build_weapon_route(tmp_path, workflow=_workflow("post_locks"))

    assert route["status"] == "not_required"
    assert route["demand_detected"] is False


def test_bulk_motion_demand_auto_selects_verified_wan_weapon(tmp_path: Path) -> None:
    route = build_weapon_route(
        tmp_path,
        workflow=_workflow("bulk"),
        primary_job={"skillId": "image.animate"},
    )

    assert route["status"] == "ready"
    assert route["weapon_id"] == "wan22-i2v-quality"
    assert route["provider"] == "comfy-wan22"


def test_adult_bulk_motion_fails_closed_without_promoted_meat_weapon(
    tmp_path: Path,
) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "adult"}),
        encoding="utf-8",
    )

    route = build_weapon_route(
        tmp_path,
        workflow=_workflow("bulk"),
        primary_job={"skillId": "image.animate"},
    )

    assert route["status"] == "blocked"
    assert route["fail_closed"] is True
    assert "no promoted Wan 2.2 weapon" in route["reason"]


def test_compact_and_full_dispatch_share_weapon_route(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t","theme":"x"}\n', encoding="utf-8")

    full = build_dispatch(
        tmp_path,
        gates={},
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )
    compact = compact_dispatch(full)

    assert compact["weapon_route"] == full["weapon_route"]
