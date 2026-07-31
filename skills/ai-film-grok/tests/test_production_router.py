from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import main  # noqa: E402
from production_router import (  # noqa: E402
    RouteExplainError,
    explain_route,
    plan_route,
    preflight_route_plan,
)

NOW = "2026-07-28T12:00:00+00:00"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_spec(root: Path, shots: list[dict[str, object]], **extra: object) -> None:
    if "i2v_provider" in extra and "_i2v_provider_explicit" not in extra:
        extra["_i2v_provider_explicit"] = True
    _write_json(
        root / "film-spec.json",
        {
            "title": "route fixture",
            "genre": "drama",
            "scenes": [{"id": "scene01", "shots": shots}],
            **extra,
        },
    )


def _capability(
    capability_id: str,
    *,
    provider: str,
    model: str,
    operations: list[str],
    shot_roles: list[str],
    status: str = "ready",
    expires_at: str = "2026-07-29T12:00:00+00:00",
    priority: int = 50,
    quality_floor: int = 4,
    quality_score: int = 4,
    content_classes: list[str] | None = None,
    pilot_verified: bool = True,
    experimental: bool = False,
) -> dict[str, object]:
    return {
        "id": capability_id,
        "provider": provider,
        "model": model,
        "operations": operations,
        "shot_roles": shot_roles,
        "content_classes": content_classes or ["general"],
        "status": status,
        "verified_at": "2026-07-28T10:00:00+00:00",
        "expires_at": expires_at,
        "authorization": "ready",
        "pilot_verified": pilot_verified,
        "experimental": experimental,
        "identity_lock_supported": "hero" in shot_roles,
        "quality_floor": quality_floor,
        "quality_score": quality_score,
        "priority": priority,
        "resource": f"{provider}:default",
        "concurrency": 1,
        "cost_state": "unknown",
    }


def _write_capabilities(
    root: Path,
    capabilities: list[dict[str, object]],
    *,
    bind_route_evidence: bool = True,
) -> Path:
    rows = [dict(item) for item in capabilities]
    if bind_route_evidence:
        for item in rows:
            provider = str(item.get("provider") or "").lower()
            model = str(item.get("model") or "").lower()
            operations = set(item.get("operations") or [])
            payload: dict[str, object] | None = None
            if (
                provider == "frw"
                and re.search(r"(?:^|/)wan(?:[0-9._-]|$)", model)
                and "image_to_video" in operations
            ):
                output = root / "out" / f"{item['id']}.mp4"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"media:{item['id']}".encode())
                payload = {
                    "ok": True,
                    "model": model,
                    "output": str(output.relative_to(root)),
                    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                    "full_decode_ok": True,
                    "human_review": "approved",
                }
            elif provider.startswith(("comfy", "local")) and "image_to_video" in operations:
                payload = {
                    "kind": "comfy-submission-capacity",
                    "ok": True,
                    "floors": {
                        "ram_free_bytes": 12 * 1024**3,
                        "vram_free_bytes": 24 * 1024**3,
                    },
                    "observed": {
                        "ram_free_bytes": 16 * 1024**3,
                        "device": {"vram_free_bytes": 28 * 1024**3},
                        "queue": {"running": 0, "pending": 0},
                    },
                }
            if payload is not None:
                receipt = root / "receipts" / "capability-evidence" / f"{item['id']}.json"
                _write_json(receipt, payload)
                item["receipt_path"] = str(receipt.relative_to(root))
                item["receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    path = root / "receipts" / "capability-snapshot.json"
    _write_json(
        path,
        {
            "schema_version": 1,
            "kind": "ai-film-capability-snapshot",
            "generated_at": "2026-07-28T10:00:00+00:00",
            "capabilities": rows,
        },
    )
    return path


def test_env_shot_selects_specialized_cloud_t2v_and_explains_rejections(
    tmp_path: Path,
) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "env"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "frw-env",
                provider="frw",
                model="ltx-t2v",
                operations=["text_to_video"],
                shot_roles=["env", "bridge", "insert"],
                priority=80,
            ),
            _capability(
                "wan-hero",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=100,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["ok"] is True
    assert report["read_only"] is True
    assert report["selected"]["capability_id"] == "frw-env"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "SHOT_ROLE_UNSUPPORTED" in rejected["wan-hero"]
    assert report["selection_policy"] == [
        "hard_constraints",
        "action_provider_priority",
        "quality_floor",
        "quality_score",
        "role_affinity",
        "priority",
        "stable_id",
    ]


def test_action_shot_obeys_ltx_grok_frw_wan_local_priority(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local-wan",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                quality_floor=5,
                quality_score=5,
            ),
            _capability(
                "grok-i2v",
                provider="grok",
                model="grok-imagine-video",
                operations=["image_to_video"],
                shot_roles=["hero"],
                quality_floor=5,
                quality_score=5,
            ),
            _capability(
                "frw-ltx",
                provider="frw",
                model="ltx-2.3",
                operations=["image_to_video"],
                shot_roles=["hero"],
                quality_floor=4,
                quality_score=4,
            ),
            _capability(
                "frw-wan",
                provider="frw",
                model="wan-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                quality_floor=5,
                quality_score=5,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["selected"]["capability_id"] == "frw-ltx"
    assert report["selected"]["rank"]["action_provider_priority"] == 4
    assert report["selected"]["rank"]["role_affinity"] == 2
    assert [item["capability_id"] for item in report["alternatives"]] == [
        "grok-i2v",
        "frw-wan",
        "local-wan",
    ]


def test_auto_ltx_default_is_not_a_hard_lock_when_ltx_is_blocked(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        [{"id": "shot01", "shot_role": "hero"}],
        i2v_provider="frw-ltx23",
        _i2v_provider_explicit=False,
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "frw-ltx",
                provider="frw",
                model="ltx-2.3",
                operations=["image_to_video"],
                shot_roles=["hero"],
                status="blocked",
            ),
            _capability(
                "grok-i2v",
                provider="grok",
                model="grok-imagine-video",
                operations=["image_to_video"],
                shot_roles=["hero"],
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["selected"]["capability_id"] == "grok-i2v"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "CAPABILITY_NOT_READY" in rejected["frw-ltx"]


def test_wan_and_local_routes_fail_closed_without_bound_evidence(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "fake-frw-wan",
                provider="frw",
                model="not-wan",
                operations=["image_to_video"],
                shot_roles=["hero"],
            ),
            _capability(
                "local-wan",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
            ),
        ],
        bind_route_evidence=False,
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["selected"] is None
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "ACTION_PROVIDER_NOT_IN_CHAIN" in rejected["fake-frw-wan"]
    assert "CAPABILITY_EVIDENCE_UNBOUND" in rejected["local-wan"]


def test_speaking_shot_route_exposes_serial_competition_dag_and_fails_closed(
    tmp_path: Path,
) -> None:
    _write_spec(
        tmp_path,
        [
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
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "wan22-i2v",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
            )
        ],
    )

    report = plan_route(tmp_path, shot_id="line01", now=NOW)

    competition = report["route_plan"]["dialogue_competition"]
    assert report["ok"] is False
    assert report["blocked_reason"] == "DIALOGUE_COMPETITION_BLOCKED"
    assert [step["id"] for step in competition["dag"]["steps"]] == [
        "state_i2i",
        "tts",
        "primary_infinite_talk",
        "secondary_grok_imagine",
        "secondary_lipsync",
        "qa",
        "provisional_select",
        "human_approve",
        "promote",
    ]
    assert len(report["execution_plan"]["tasks"]) == 9
    assert report["execution_plan"]["tasks"][3]["run_condition"] == (
        "when_explicit_secondary_or_primary_technical_failure"
    )
    assert all(task["status"] == "blocked" for task in report["execution_plan"]["tasks"])
    assert report["execution_plan"]["authorized"] is False

    production_report = plan_route(
        tmp_path,
        shot_id="line01",
        quality_tier="select",
        now=NOW,
    )
    assert "DIALOGUE_ROUTE_NOT_PROMOTED" in {
        issue["code"] for issue in production_report["route_plan"]["dialogue_competition"]["issues"]
    }


def test_speaking_shot_selects_infinite_talk_and_exposes_grok_audio_linked_secondary(
    tmp_path: Path,
) -> None:
    _write_spec(
        tmp_path,
        [
            {
                "id": "line01",
                "shot_role": "hero",
                "screen_mode": "on_camera",
                "speaker_on_camera": True,
                "lipsync": True,
                "dialogue_motion_route": "auto",
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
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "qwen-image-i2i",
                provider="comfy-qwen",
                model="qwen-image-i2i",
                operations=["image_to_image"],
                shot_roles=["hero"],
            ),
            _capability(
                "edge-ja",
                provider="edge",
                model="edge-ja",
                operations=["text_to_speech"],
                shot_roles=["hero"],
            ),
            _capability(
                "infinitetalk",
                provider="comfy-infinitetalk",
                model="infinitetalk",
                operations=["face_animation_to_audio"],
                shot_roles=["hero"],
            ),
            _capability(
                "grok-imagine-video",
                provider="grok",
                model="imagine-video",
                operations=["image_to_video"],
                shot_roles=["hero"],
            ),
            _capability(
                "latentsync-1.6",
                provider="comfy-latentsync",
                model="latentsync-1.6",
                operations=["video_lip_sync"],
                shot_roles=["hero"],
            ),
        ],
    )
    _write_json(
        tmp_path / "receipts" / "comfy-capacity.json",
        {"queue_known": True, "busy": False},
    )

    report = explain_route(tmp_path, shot_id="line01", now=NOW)

    assert report["ok"] is True
    assert report["selected"]["capability_id"] == "infinitetalk"
    assert report["selected"]["dialogue_motion_route"] == "infinite_talk"
    assert report["selected"]["route_chain"] == ["infinitetalk"]
    competition = report["dialogue_competition"]
    assert competition["secondary_available"] is True
    assert competition["candidates"][1]["models"] == [
        "imagine-video",
        "latentsync-1.6",
    ]
    assert competition["route_policy"]["forbidden_secondary_triggers"] == [
        "human_quality_rejection",
        "unknown_error",
        "identity_drift",
    ]


def test_dialogue_broll_routes_as_a_timed_editorial_child(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        [
            {
                "id": "line01",
                "shot_role": "hero",
                "dsl": {"motion": "locked close-up"},
                "dialogue_broll": [
                    {
                        "id": "line01__broll01",
                        "kind": "insert",
                        "parent_shot_id": "line01",
                        "shot_role": "insert",
                        "audio_policy": "carry_parent_dialogue",
                        "speaker_on_camera": False,
                        "lipsync": False,
                        "dsl": {"motion": "small object movement"},
                    }
                ],
            }
        ],
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "t2v-insert",
                provider="grok",
                model="image-to-video",
                operations=["text_to_video"],
                shot_roles=["env", "insert"],
            )
        ],
    )

    report = explain_route(tmp_path, shot_id="line01__broll01", now=NOW)

    assert report["ok"] is True
    assert report["selected"]["capability_id"] == "t2v-insert"
    assert report["intent"]["parent_shot_id"] == "line01"
    assert report["intent"]["editorial_only"] is True
    assert report["intent"]["audio_policy"] == "carry_parent_dialogue"


def test_restricted_identity_shot_routes_local_and_rejects_cloud(
    tmp_path: Path,
) -> None:
    _write_spec(
        tmp_path,
        [
            {
                "id": "shot01",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "dsl": {"cast": ["heroine"]},
            }
        ],
        genre="adult",
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "grok-hero",
                provider="grok",
                model="video-1.5",
                operations=["image_to_video"],
                shot_roles=["hero"],
                priority=100,
            ),
            _capability(
                "wan-local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=70,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["intent"]["content_class"] == "restricted_local"
    assert report["intent"]["identity_lock"] is True
    assert report["selected"]["capability_id"] == "wan-local"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "CONTENT_CLASS_UNSUPPORTED" in rejected["grok-hero"]


def test_sensitive_shot_fields_fail_closed_even_when_genre_is_mislabeled(
    tmp_path: Path,
) -> None:
    _write_spec(
        tmp_path,
        [
            {
                "id": "shot01",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
            }
        ],
        genre="drama",
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "cloud-general",
                provider="grok",
                model="video-1.5",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general"],
                priority=100,
            ),
            _capability(
                "local-restricted",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["restricted_local"],
                priority=1,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["intent"]["content_class"] == "restricted_local"
    assert report["selected"]["capability_id"] == "local-restricted"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "CONTENT_CLASS_UNSUPPORTED" in rejected["cloud-general"]


def test_expired_capability_fails_closed_even_when_it_has_highest_score(
    tmp_path: Path,
) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "expired",
                provider="grok",
                model="video-1.5",
                operations=["image_to_video"],
                shot_roles=["hero"],
                expires_at="2026-07-28T11:59:59+00:00",
                priority=999,
                quality_score=5,
            ),
            _capability(
                "current",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=1,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["selected"]["capability_id"] == "current"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "CAPABILITY_STALE" in rejected["expired"]


def test_experimental_capability_requires_explicit_explain_opt_in(
    tmp_path: Path,
) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "experimental",
                provider="comfy-wan22",
                model="wan-experimental",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=999,
                experimental=True,
            ),
            _capability(
                "champion",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=10,
            ),
        ],
    )

    default = explain_route(tmp_path, shot_id="shot01", now=NOW)
    opted_in = explain_route(
        tmp_path,
        shot_id="shot01",
        now=NOW,
        allow_experimental=True,
    )

    assert default["selected"]["capability_id"] == "champion"
    assert "EXPERIMENTAL_NOT_ALLOWED" in default["rejected"][0]["reasons"]
    assert opted_in["selected"]["capability_id"] == "experimental"
    assert opted_in["selected"]["requires_human_approval"] is True
    assert opted_in["auto_execute"] is False


def test_provider_lock_is_a_hard_constraint_for_hero_motion(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        [{"id": "shot01", "shot_role": "hero"}],
        i2v_provider="grok",
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=100,
            ),
            _capability(
                "grok",
                provider="grok",
                model="video-1.5",
                operations=["image_to_video"],
                shot_roles=["hero"],
                priority=1,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["selected"]["provider"] == "grok"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "PROVIDER_LOCK_MISMATCH" in rejected["local"]


def test_shot_auto_cannot_clear_an_explicit_film_provider_lock(
    tmp_path: Path,
) -> None:
    _write_spec(
        tmp_path,
        [{"id": "shot01", "shot_role": "hero", "i2v_provider": "auto"}],
        i2v_provider="grok",
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
                priority=100,
            ),
            _capability(
                "grok",
                provider="grok",
                model="video-1.5",
                operations=["image_to_video"],
                shot_roles=["hero"],
                priority=1,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["intent"]["provider_lock"] == "grok"
    assert report["selected"]["provider"] == "grok"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "PROVIDER_LOCK_MISMATCH" in rejected["local"]


def test_explicit_shot_provider_lock_overrides_the_film_default(
    tmp_path: Path,
) -> None:
    _write_spec(
        tmp_path,
        [{"id": "shot01", "shot_role": "hero", "i2v_provider": "frw"}],
        i2v_provider="grok",
    )
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "frw",
                provider="frw",
                model="seedance-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                priority=1,
            ),
            _capability(
                "grok",
                provider="grok",
                model="video-1.5",
                operations=["image_to_video"],
                shot_roles=["hero"],
                priority=100,
            ),
        ],
    )

    report = explain_route(tmp_path, shot_id="shot01", now=NOW)

    assert report["intent"]["provider_lock"] == "frw"
    assert report["selected"]["provider"] == "frw"
    rejected = {item["capability_id"]: item["reasons"] for item in report["rejected"]}
    assert "PROVIDER_LOCK_MISMATCH" in rejected["grok"]


def test_missing_snapshot_and_unknown_shot_fail_with_typed_errors(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])

    with pytest.raises(RouteExplainError, match="CAPABILITY_SNAPSHOT_MISSING"):
        explain_route(tmp_path, shot_id="shot01", now=NOW)

    _write_capabilities(tmp_path, [])
    with pytest.raises(RouteExplainError, match="SHOT_NOT_FOUND"):
        explain_route(tmp_path, shot_id="missing", now=NOW)


def test_explain_is_deterministic_and_does_not_write_receipts(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    snapshot = _write_capabilities(
        tmp_path,
        [
            _capability(
                "b",
                provider="comfy-wan22",
                model="wan-b",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            ),
            _capability(
                "a",
                provider="comfy-wan22",
                model="wan-a",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            ),
        ],
    )
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    first = explain_route(tmp_path, shot_id="shot01", now=NOW)
    second = explain_route(
        tmp_path,
        shot_id="shot01",
        now=NOW,
        capabilities_path=snapshot,
    )
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    assert first == second
    assert first["selected"]["capability_id"] == "a"
    assert before == after


def test_generated_contracts_validate_against_public_schemas(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    snapshot_path = _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )
    report = explain_route(tmp_path, shot_id="shot01", now=NOW)
    schema_root = Path(__file__).resolve().parents[1] / "schemas"

    jsonschema.validate(
        json.loads(snapshot_path.read_text()),
        json.loads((schema_root / "capability-snapshot.schema.json").read_text()),
    )
    jsonschema.validate(
        report["intent"],
        json.loads((schema_root / "shot-intent.schema.json").read_text()),
    )
    jsonschema.validate(
        report,
        json.loads((schema_root / "route-plan.schema.json").read_text()),
    )


def test_non_motion_domain_is_not_eligible_for_shot_routing(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    capability = _capability(
        "still-only",
        provider="comfy-lan",
        model="qwen-image",
        operations=["image_to_video"],
        shot_roles=["hero"],
    )
    capability["domains"] = ["visual_still"]
    _write_capabilities(tmp_path, [capability])
    report = explain_route(tmp_path, shot_id="shot01", now=NOW)
    assert report["ok"] is False
    assert report["rejected"][0]["reasons"] == ["CAPABILITY_NOT_MOTION_ROUTE"]


@pytest.mark.parametrize(
    ("patch", "error"),
    [
        ({"schema_version": 2}, "schema_version"),
        (
            {
                "capabilities": [
                    _capability(
                        "duplicate",
                        provider="grok",
                        model="one",
                        operations=["image_to_video"],
                        shot_roles=["hero"],
                    ),
                    _capability(
                        "duplicate",
                        provider="grok",
                        model="two",
                        operations=["image_to_video"],
                        shot_roles=["hero"],
                    ),
                ]
            },
            "duplicate capability id",
        ),
    ],
)
def test_invalid_snapshot_contract_fails_closed(
    tmp_path: Path,
    patch: dict[str, object],
    error: str,
) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    path = _write_capabilities(tmp_path, [])
    snapshot = json.loads(path.read_text())
    snapshot.update(patch)
    _write_json(path, snapshot)

    with pytest.raises(RouteExplainError, match=error):
        explain_route(tmp_path, shot_id="shot01", now=NOW)


def test_cli_route_explain_is_wired_and_preserves_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )
    before = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    code = main(
        [
            "route",
            "explain",
            "--root",
            str(tmp_path),
            "--shot-id",
            "shot01",
            "--now",
            NOW,
        ]
    )

    output = json.loads(capsys.readouterr().out)
    after = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert code == 0
    assert output["selected"]["capability_id"] == "local"
    assert before == after


def test_route_plan_preview_is_read_only_and_never_authorizes(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )
    before = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    report = plan_route(tmp_path, shot_id="shot01", now=NOW)

    after = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    execution = report["execution_plan"]
    assert report["ok"] is True
    assert report["read_only"] is True
    assert report["written"] is False
    assert execution["authorized"] is False
    assert execution["tasks"][0]["status"] == "planned"
    assert before == after


def test_route_plan_write_persists_hash_bound_receipts(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )

    report = plan_route(tmp_path, shot_id="shot01", now=NOW, write=True)

    assert report["ok"] is True
    assert report["read_only"] is False
    assert report["written"] is True
    route_path = Path(report["receipts"]["route_plan"])
    execution_path = Path(report["receipts"]["execution_plan"])
    assert route_path.is_file()
    assert execution_path.is_file()
    assert (
        report["execution_plan"]["route_plan_sha256"]
        == __import__("hashlib").sha256(route_path.read_bytes()).hexdigest()
    )
    jsonschema.Draft202012Validator(
        json.loads((SCRIPTS.parent / "schemas" / "execution-plan.schema.json").read_text())
    ).validate(json.loads(execution_path.read_text()))
    assert not (tmp_path / "receipts" / "media-queue.json").exists()


def test_route_plan_refuses_to_write_when_no_capability_is_viable(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "cloud-only",
                provider="grok",
                model="video-1.5",
                operations=["text_to_video"],
                shot_roles=["env"],
            )
        ],
    )

    report = plan_route(tmp_path, shot_id="shot01", now=NOW, write=True)

    assert report["ok"] is False
    assert report["written"] is False
    assert report["blocked_reason"] == "NO_VIABLE_CAPABILITY"
    assert not (tmp_path / "receipts" / "route-plans").exists()


def test_route_plan_write_rejects_unsafe_shot_id(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "../escape", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )

    with pytest.raises(RouteExplainError, match="INVALID_ROUTE_PLAN"):
        plan_route(tmp_path, shot_id="../escape", now=NOW, write=True)

    assert not (tmp_path.parent / "escape").exists()


def test_cli_route_plan_write_is_explicit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )

    code = main(
        [
            "route",
            "plan",
            "--root",
            str(tmp_path),
            "--shot-id",
            "shot01",
            "--now",
            NOW,
            "--write",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["written"] is True
    assert output["execution_plan"]["authorized"] is False


def test_route_preflight_is_read_only_and_ready_for_human_authorization(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    capability = _capability(
        "local",
        provider="comfy-wan22",
        model="wan22-i2v",
        operations=["image_to_video"],
        shot_roles=["hero"],
        content_classes=["general", "restricted_local"],
    )
    capability["cost_state"] = "free_local"
    _write_capabilities(tmp_path, [capability])
    planned = plan_route(tmp_path, shot_id="shot01", now=NOW, write=True)
    before = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    report = preflight_route_plan(
        tmp_path,
        route_plan_path=Path(planned["receipts"]["route_plan"]),
        execution_plan_path=Path(planned["receipts"]["execution_plan"]),
        now=NOW,
    )

    after = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert report["ok"] is True
    assert report["read_only"] is True
    assert report["authorized"] is False
    assert report["ready_for_human_authorization"] is True
    assert before == after


def test_route_preflight_blocks_unknown_cost(tmp_path: Path) -> None:
    _write_spec(tmp_path, [{"id": "shot01", "shot_role": "hero"}])
    _write_capabilities(
        tmp_path,
        [
            _capability(
                "local",
                provider="comfy-wan22",
                model="wan22-i2v",
                operations=["image_to_video"],
                shot_roles=["hero"],
                content_classes=["general", "restricted_local"],
            )
        ],
    )
    planned = plan_route(tmp_path, shot_id="shot01", now=NOW, write=True)

    report = preflight_route_plan(
        tmp_path,
        route_plan_path=Path(planned["receipts"]["route_plan"]),
        execution_plan_path=Path(planned["receipts"]["execution_plan"]),
        now=NOW,
    )

    assert report["ok"] is False
    assert "COST_STATE_UNKNOWN" in report["blockers"]
