from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import main  # noqa: E402
from production_team import scaffold_team, validate_team  # noqa: E402


def _snapshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "ai-film-capability-snapshot",
                "generated_at": "2026-07-29T00:00:00+00:00",
                "capabilities": [
                    {
                        "id": "rtx-motion",
                        "provider": "comfy-wan22",
                        "model": "wan22-i2v",
                        "operations": ["image_to_video"],
                        "shot_roles": ["hero"],
                        "content_classes": ["general"],
                        "status": "ready",
                        "verified_at": "2026-07-29T00:00:00+00:00",
                        "expires_at": "2026-07-30T00:00:00+00:00",
                        "authorization": "ready",
                        "pilot_verified": True,
                        "experimental": False,
                        "identity_lock_supported": True,
                        "quality_floor": 4,
                        "quality_score": 4,
                        "priority": 10,
                        "resource": "gpu:rtx5090",
                        "concurrency": 1,
                        "cost_state": "free_local",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_scaffold_requires_explicit_assignments_before_ready(tmp_path: Path) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    written = scaffold_team(tmp_path, capabilities_path=snapshot)
    assert Path(written["written"]).is_file()
    result = validate_team(written["written"], capabilities_path=snapshot)
    assert result["ok"] is False
    assert "NO_MODEL_OR_TOOL_ASSIGNED:cinematography" in result["blockers"]


def test_team_validation_accepts_complete_explicit_roster(tmp_path: Path) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    plan_path = Path(scaffold_team(tmp_path, capabilities_path=snapshot)["written"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for assignment in plan["assignments"]:
        assignment["local_tools"] = ["m1-controlled-tool"]
    plan["assignments"][1]["model_capability_ids"] = ["rtx-motion"]
    unsigned = {key: value for key, value in plan.items() if key != "content_sha256"}
    from util import canonical_json_sha256

    plan["content_sha256"] = canonical_json_sha256(unsigned)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    result = validate_team(plan_path, capabilities_path=snapshot)
    assert result["ok"] is True


def test_team_cli_validation_reports_changed_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    plan_path = Path(scaffold_team(tmp_path, capabilities_path=snapshot)["written"])
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["generated_at"] = "2026-07-29T01:00:00+00:00"
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        main(["team", "validate", "--plan", str(plan_path), "--capabilities", str(snapshot)]) == 2
    )
    assert "CAPABILITY_SNAPSHOT_CHANGED" in capsys.readouterr().out
