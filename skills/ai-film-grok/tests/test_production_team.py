from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import main  # noqa: E402
from production_router import explain_route  # noqa: E402
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


def test_snapshot_projects_dialogue_motion_operations_for_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import comfy_armory
    import compose_render
    import lipsync_backend
    import tts_backend

    monkeypatch.setattr(
        comfy_armory,
        "load_armory",
        lambda: {
            "weapons": [
                {
                    "id": "qwen-image-edit-2511-local",
                    "display_name": "Qwen Image Edit",
                    "provider": "comfy_lan",
                    "status": "verified",
                    "intents": ["image-edit"],
                    "verified": {"real_pilot": True},
                },
                {
                    "id": "infinite-talk-stable-pilot",
                    "display_name": "InfiniteTalk",
                    "provider": "comfy_lan",
                    "status": "experimental",
                    "intents": ["talking-avatar-stable-pilot"],
                    "verified": {"real_pilot": True},
                },
            ]
        },
    )
    monkeypatch.setattr(
        comfy_armory,
        "probe_armory",
        lambda _url: {
            "ok": True,
            "ready_ids": ["qwen-image-edit-2511-local", "infinite-talk-stable-pilot"],
        },
    )
    monkeypatch.setattr(compose_render, "probe_designed_post_tooling", lambda: {})
    monkeypatch.setattr(
        tts_backend,
        "probe",
        lambda: {"backends": {"edge": True}, "audio_node": {"ok": False}},
    )
    monkeypatch.setattr(
        lipsync_backend,
        "probe",
        lambda: {
            "node": {
                "ok": True,
                "backends": {
                    "latentsync": {
                        "ready": True,
                        "approved": True,
                        "model": "LatentSync 1.6",
                    }
                },
            },
            "ready": ["latentsync"],
        },
    )
    snapshot_path = tmp_path / "receipts" / "capability-snapshot.json"
    snapshot = snapshot_capabilities(out=snapshot_path)
    capabilities = {item["id"]: item for item in snapshot["snapshot"]["capabilities"]}

    assert capabilities["rtx5090-qwen-image-edit-2511-local"]["operations"] == ["image_to_image"]
    assert capabilities["rtx5090-infinite-talk-stable-pilot"]["operations"] == [
        "face_animation_to_audio"
    ]
    assert capabilities["edge-ja"]["operations"] == ["text_to_speech"]
    assert capabilities["rtx5090-lipsync-latentsync"]["operations"] == ["video_lip_sync"]
    assert capabilities["grok-imagine-video"]["pilot_verified"] is False

    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "dialogue routing",
                "genre": "drama",
                "scenes": [
                    {
                        "id": "scene01",
                        "shots": [
                            {
                                "id": "line01",
                                "shot_role": "hero",
                                "screen_mode": "on_camera",
                                "speaker_on_camera": True,
                                "lipsync": True,
                                "speaker": "hero",
                                "performance_intent": {"emotion": "guarded"},
                                "performance_state": {
                                    "status": "approved",
                                    "image_sha256": "a" * 64,
                                },
                                "tts": {
                                    "status": "final",
                                    "language": "ja",
                                    "audio_sha256": "b" * 64,
                                },
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "receipts" / "comfy-capacity.json").write_text(
        json.dumps({"queue_known": True, "busy": False}), encoding="utf-8"
    )

    route = explain_route(
        tmp_path,
        shot_id="line01",
        now=snapshot["snapshot"]["generated_at"],
    )

    assert route["ok"] is True, route["dialogue_competition"].get("issues")
    assert route["selected"]["capability_id"] == "rtx5090-infinite-talk-stable-pilot"
    assert route["dialogue_competition"]["selected_route"] == "infinite_talk"
    assert route["dialogue_competition"]["secondary_available"] is False


def test_snapshot_blocks_local_i2v_below_live_capacity_floor_and_binds_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import comfy_armory
    import comfy_video
    import compose_render
    import lipsync_backend
    import tts_backend

    monkeypatch.setattr(
        comfy_armory,
        "load_armory",
        lambda: {
            "weapons": [
                {
                    "id": "wan22-i2v-quality",
                    "display_name": "Wan 2.2 I2V official quality",
                    "provider": "comfy-wan22",
                    "status": "verified",
                    "intents": ["image-to-video"],
                    "verified": {"real_pilot": True},
                }
            ]
        },
    )
    monkeypatch.setattr(
        comfy_armory,
        "probe_armory",
        lambda _url: {
            "ok": True,
            "base_url": "http://127.0.0.1:18188",
            "ready_ids": ["wan22-i2v-quality"],
        },
    )
    capacity = {
        "schema_version": 1,
        "kind": "comfy-submission-capacity",
        "ok": False,
        "status": "blocked",
        "floors": {
            "ram_free_bytes": 12 * 1024**3,
            "vram_free_bytes": 24 * 1024**3,
            "queue_must_be_idle": True,
        },
        "observed": {
            "ram_free_bytes": 20 * 1024**3,
            "device": {"vram_free_bytes": 16 * 1024**3},
            "queue": {"running": 0, "pending": 0},
        },
        "blockers": [{"code": "VRAM_BELOW_FLOOR"}],
    }
    monkeypatch.setattr(comfy_video, "submission_capacity", lambda _url: capacity)
    monkeypatch.setattr(compose_render, "probe_designed_post_tooling", lambda: {})
    monkeypatch.setattr(lipsync_backend, "probe", lambda: {})
    monkeypatch.setattr(tts_backend, "probe", lambda: {})

    destination = tmp_path / "receipts" / "capability-snapshot.json"
    result = snapshot_capabilities(out=destination)
    local = next(
        item
        for item in result["snapshot"]["capabilities"]
        if item["id"] == "rtx5090-wan22-i2v-quality"
    )

    assert local["status"] == "blocked"
    assert local["authorization"] == "unknown"
    receipt = tmp_path / local["receipt_path"]
    assert receipt.is_file()
    assert local["receipt_sha256"] == __import__("hashlib").sha256(receipt.read_bytes()).hexdigest()
    assert result["observations"]["rtx5090_capacity"]["ok"] is False
    assert result["observations"]["rtx5090_capacity"]["blockers"] == ["VRAM_BELOW_FLOOR"]


def test_snapshot_lists_full_action_chain_with_film_scoped_canary_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import comfy_armory
    import compose_render
    import i2v_provider
    import lipsync_backend
    import tts_backend

    monkeypatch.setattr(comfy_armory, "load_armory", lambda: {"weapons": []})
    monkeypatch.setattr(
        comfy_armory,
        "probe_armory",
        lambda _url: {
            "ok": True,
            "base_url": "http://127.0.0.1:18188",
            "ready_ids": [],
        },
    )
    monkeypatch.setattr(compose_render, "probe_designed_post_tooling", lambda: {})
    monkeypatch.setattr(lipsync_backend, "probe", lambda: {})
    monkeypatch.setattr(tts_backend, "probe", lambda: {})

    root = tmp_path
    receipts = root / "receipts"
    receipts.mkdir()
    canaries = {
        "grok": receipts / "grok-i2v-canary.json",
        "frw-ltx23": receipts / "frw-ltx23-i2v-audio-canary.json",
        "frw-wan": receipts / "frw-wan-i2v-canary.json",
    }
    for path in canaries.values():
        path.write_text('{"ok":true}\n', encoding="utf-8")

    reports = {
        "grok": i2v_provider.CapabilityReport(
            provider="grok",
            ok=True,
            available=True,
            reason="approved",
            models=["grok-imagine-video"],
            profile="grok_primary",
            detail={"receipt": str(canaries["grok"])},
        ),
        "frw-ltx23": i2v_provider.CapabilityReport(
            provider="frw-ltx23",
            ok=True,
            available=True,
            reason="approved",
            models=["ltx-2.3", "img2video-audio"],
            profile="ltx23_primary",
            detail={"receipt": str(canaries["frw-ltx23"])},
        ),
        "frw-wan": i2v_provider.CapabilityReport(
            provider="frw-wan",
            ok=True,
            available=True,
            reason="approved",
            models=["wan"],
            profile="frw_wan_fallback",
            detail={"receipt": str(canaries["frw-wan"])},
        ),
    }
    monkeypatch.setattr(
        i2v_provider.GrokI2VProvider,
        "probe",
        lambda _self, **_kwargs: reports["grok"],
    )
    monkeypatch.setattr(
        i2v_provider.FrwLtx23AudioProvider,
        "probe",
        lambda _self, **_kwargs: reports["frw-ltx23"],
    )
    monkeypatch.setattr(
        i2v_provider.FrwWanProvider,
        "probe",
        lambda _self, **_kwargs: reports["frw-wan"],
    )

    result = snapshot_capabilities(out=receipts / "capability-snapshot.json")
    capabilities = {item["provider"]: item for item in result["snapshot"]["capabilities"]}

    assert capabilities["frw-ltx23"]["pilot_verified"] is True
    assert capabilities["grok"]["pilot_verified"] is True
    assert capabilities["frw-wan"]["pilot_verified"] is True
    for provider in ("frw-ltx23", "grok", "frw-wan"):
        assert capabilities[provider]["receipt_path"] == str(canaries[provider].relative_to(root))
        assert len(capabilities[provider]["receipt_sha256"]) == 64
