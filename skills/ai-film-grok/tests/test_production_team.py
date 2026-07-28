from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import main  # noqa: E402
from production_team import scaffold_team, snapshot_capabilities, validate_team  # noqa: E402


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
    assert "NO_MODEL_ASSIGNED:cinematography" in result["blockers"]


def test_team_validation_accepts_complete_explicit_roster(tmp_path: Path) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    plan_path = Path(scaffold_team(tmp_path, capabilities_path=snapshot)["written"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for assignment in plan["assignments"]:
        assignment["model_capability_ids"] = ["rtx-motion"]
    unsigned = {key: value for key, value in plan.items() if key != "content_sha256"}
    from util import canonical_json_sha256

    plan["content_sha256"] = canonical_json_sha256(unsigned)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    result = validate_team(plan_path, capabilities_path=snapshot)
    assert result["ok"] is True


def test_team_validation_rejects_wrong_director_domain(tmp_path: Path) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["capabilities"][0]["domains"] = ["visual_still"]
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    plan_path = Path(scaffold_team(tmp_path, capabilities_path=snapshot)["written"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for assignment in plan["assignments"]:
        assignment["model_capability_ids"] = ["rtx-motion"]
    from util import canonical_json_sha256

    plan["content_sha256"] = canonical_json_sha256(
        {key: value for key, value in plan.items() if key != "content_sha256"}
    )
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    result = validate_team(plan_path, capabilities_path=snapshot)
    assert result["ok"] is False
    assert "CAPABILITY_DOMAIN_MISMATCH:rtx-motion:showrunner" in result["blockers"]


def test_team_validation_rejects_experimental_assignment(tmp_path: Path) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["capabilities"][0]["experimental"] = True
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    plan_path = Path(scaffold_team(tmp_path, capabilities_path=snapshot)["written"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for assignment in plan["assignments"]:
        assignment["model_capability_ids"] = ["rtx-motion"]
    from util import canonical_json_sha256

    plan["content_sha256"] = canonical_json_sha256(
        {key: value for key, value in plan.items() if key != "content_sha256"}
    )
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    result = validate_team(plan_path, capabilities_path=snapshot)
    assert result["ok"] is False
    assert "EXPERIMENTAL_CAPABILITY:rtx-motion:showrunner" in result["blockers"]


def test_stage_validation_only_checks_owning_directors(tmp_path: Path) -> None:
    snapshot = tmp_path / "receipts" / "capabilities.json"
    _snapshot(snapshot)
    plan_path = Path(scaffold_team(tmp_path, capabilities_path=snapshot)["written"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["assignments"][0]["model_capability_ids"] = ["rtx-motion"]
    from util import canonical_json_sha256

    plan["content_sha256"] = canonical_json_sha256(
        {key: value for key, value in plan.items() if key != "content_sha256"}
    )
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    result = validate_team(plan_path, capabilities_path=snapshot, stage="script_lock")
    assert result["ok"] is True
    assert result["required_directors"] == ["showrunner"]
    assert (
        next(item for item in result["coverage"] if item["director_id"] == "sound")["required"]
        is False
    )


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


def test_snapshot_only_promotes_story_model_after_explicit_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import comfy_armory
    import compose_render
    import lipsync_backend
    import local_llm
    import tts_backend

    monkeypatch.setenv("AIFILM_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setattr(comfy_armory, "load_armory", lambda: {"weapons": []})
    monkeypatch.setattr(comfy_armory, "probe_armory", lambda _url: {"ok": True, "ready_ids": []})
    monkeypatch.setattr(compose_render, "probe_designed_post_tooling", lambda: {})
    monkeypatch.setattr(lipsync_backend, "probe", lambda: {})
    monkeypatch.setattr(tts_backend, "probe", lambda: {})
    monkeypatch.setattr(
        local_llm,
        "probe",
        lambda *_args, **_kwargs: {"ok": True, "model": "openai/gpt-oss-20b"},
    )
    monkeypatch.setattr(
        local_llm, "shot_draft", lambda *_args, **_kwargs: {"status": "candidate_only"}
    )

    result = snapshot_capabilities(out=tmp_path / "capabilities.json", verify_story=True)
    story = next(
        item for item in result["snapshot"]["capabilities"] if item["id"] == "m1-story-reasoning"
    )
    assert story["status"] == "ready"
    assert story["pilot_verified"] is True
    assert result["observations"]["m1"]["story_model"]["verified"] is True
