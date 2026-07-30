#!/usr/bin/env python3
"""Evidence-bound specialist-director roster for one film workspace.

This is deliberately an orchestration contract, not an autonomous agent runner.
It makes model ownership, review authority, and handoff evidence explicit before
any model is asked to make or modify media.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from production_router import RouteExplainError, _validate_snapshot
from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json


class ProductionTeamError(ValueError):
    """A production-team plan is missing, malformed, or no longer current."""


TEAM_VERSION = 1
DIRECTORS: tuple[dict[str, Any], ...] = (
    {
        "id": "showrunner",
        "department": "story",
        "mandate": "Protect theme, character arc, scene objective, and script lock.",
        "model_jobs": ["local LLM critique", "continuity graph analysis"],
        "domains": ["story"],
        "must_review": ["brief.json", "drama-graph.json", "film-spec.json"],
    },
    {
        "id": "cinematography",
        "department": "visual",
        "mandate": "Protect style, framing, identity, lighting, and reachable shot endpoints.",
        "model_jobs": ["prompt critique", "still and motion generation"],
        "domains": ["visual_still", "motion"],
        "must_review": ["style-bible.json", "shot visual direction", "review-shot receipt"],
    },
    {
        "id": "performance",
        "department": "performance",
        "mandate": "Protect acting beats, dialogue timing, voice identity, and truthful lip sync.",
        "model_jobs": ["TTS rehearsal", "lip-sync pilot"],
        "domains": ["voice", "lipsync"],
        "must_review": ["tts-rehearsal receipt", "shot performance", "lip-sync review"],
    },
    {
        "id": "sound",
        "department": "sound",
        "mandate": "Protect intelligible dialogue, concrete foley, changing music, and final mix audibility.",
        "model_jobs": ["voice synthesis", "music and SFX generation"],
        "domains": ["voice", "music"],
        "must_review": ["audio-bible.json", "mix report", "quiet-interval music check"],
    },
    {
        "id": "editor",
        "department": "post",
        "mandate": "Protect shot selection, rhythm, subtitles, transitions, and picture lock.",
        "model_jobs": ["selects analysis", "deterministic finishing"],
        "domains": ["post"],
        "must_review": ["dailies receipt", "rough-cut receipt", "post-bible.json"],
    },
    {
        "id": "quality",
        "department": "delivery",
        "mandate": "Reject weak evidence; require decoded media, whole-film review, and current provenance.",
        "model_jobs": ["frame and audio QA", "delivery audit"],
        "domains": ["qa"],
        "must_review": ["ffprobe", "full decode", "final human director review"],
    },
)
_DIRECTOR_IDS = frozenset(item["id"] for item in DIRECTORS)
STAGE_DIRECTORS: dict[str, tuple[str, ...]] = {
    "concept_lock": ("showrunner",),
    "script_lock": ("showrunner",),
    "department_look_lock": ("cinematography", "sound"),
    "shot_animatic_lock": ("showrunner", "cinematography", "performance", "editor"),
    "pilot_approval": ("cinematography", "performance", "sound"),
    "bulk": ("cinematography", "performance", "sound"),
    "dailies_review": ("cinematography", "performance", "quality"),
    "selects_rough_cut": ("editor", "quality"),
    "picture_lock": ("editor", "quality"),
    "post_locks": ("sound", "editor", "quality"),
    "master_lock": ("sound", "editor", "quality"),
}


def _capability(
    *,
    capability_id: str,
    provider: str,
    model: str,
    domains: list[str],
    status: str,
    pilot_verified: bool,
    resource: str,
    experimental: bool = False,
    operations: list[str] | None = None,
    cost_state: str = "free_local",
) -> dict[str, Any]:
    """Build one schema-compatible capability without overstating a pilot."""
    now = datetime.now(UTC)
    return {
        "id": capability_id,
        "provider": provider,
        "model": model,
        "domains": domains,
        "operations": operations or ["image_to_video" if "motion" in domains else "text_to_video"],
        "shot_roles": ["hero", "env", "bridge", "insert"],
        "content_classes": ["general"],
        "status": status,
        "verified_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "authorization": "ready" if status == "ready" else "unknown",
        "pilot_verified": pilot_verified,
        "experimental": experimental,
        "identity_lock_supported": "motion" in domains or "visual_still" in domains,
        "quality_floor": 4 if pilot_verified else 0,
        "quality_score": 4 if pilot_verified else 0,
        "priority": 100 if pilot_verified else 0,
        "resource": resource,
        "concurrency": 1,
        "cost_state": cost_state,
    }


def snapshot_capabilities(
    *, out: Path | str, base_url: str | None = None, verify_story: bool = False
) -> dict[str, Any]:
    """Read M1/5090 readiness into a short-lived, no-spend capability snapshot."""
    from comfy_armory import load_armory, probe_armory
    from compose_render import probe_designed_post_tooling
    from lipsync_backend import probe as probe_lipsync
    from tts_backend import probe as probe_tts

    destination = Path(out).expanduser().resolve()
    capabilities: list[dict[str, Any]] = []
    observations: dict[str, Any] = {}
    try:
        armory = load_armory()
        live_armory = probe_armory(base_url)
        ready_ids = set(live_armory.get("ready_ids") or [])
        observations["rtx5090_armory"] = {
            "ok": bool(live_armory.get("ok")),
            "ready_ids": sorted(ready_ids),
        }
        for weapon in armory.get("weapons") or []:
            if not isinstance(weapon, dict) or not isinstance(weapon.get("id"), str):
                continue
            intents = {str(item) for item in weapon.get("intents") or []}
            if any(item.startswith("talking-avatar") for item in intents):
                domains = ["lipsync"]
                operations = ["face_animation_to_audio"]
            elif "image-edit" in intents or "local-image-edit" in intents:
                domains = ["visual_still"]
                operations = ["image_to_image"]
            elif {"image-to-video", "i2v"} & intents:
                domains = ["motion"]
                operations = ["image_to_video"]
            else:
                domains = ["visual_still"]
                operations = ["text_to_video"]
            capabilities.append(
                _capability(
                    capability_id=f"rtx5090-{weapon['id']}",
                    provider=str(weapon.get("provider") or "comfy_lan"),
                    model=str(weapon.get("display_name") or weapon["id"]),
                    domains=domains,
                    status="ready" if weapon["id"] in ready_ids else "blocked",
                    pilot_verified=bool((weapon.get("verified") or {}).get("real_pilot")),
                    resource="gpu:rtx5090",
                    experimental=str(weapon.get("status")) == "experimental",
                    operations=operations,
                )
            )
    except Exception as exc:
        observations["rtx5090_armory"] = {"ok": False, "error": type(exc).__name__}

    tts = probe_tts()
    audio_node = tts.get("audio_node") if isinstance(tts.get("audio_node"), dict) else {}
    audio_detail = audio_node.get("detail") if isinstance(audio_node.get("detail"), dict) else {}
    audio_models = (
        audio_detail.get("models") if isinstance(audio_detail.get("models"), dict) else {}
    )
    observations["rtx5090_audio"] = {"ok": bool(audio_node.get("ok")), "models": audio_models}
    edge_ready = bool((tts.get("backends") or {}).get("edge"))
    capabilities.append(
        _capability(
            capability_id="edge-ja",
            provider="edge",
            model="ja-JP-NanamiNeural",
            domains=["voice"],
            status="ready" if edge_ready else "blocked",
            pilot_verified=edge_ready,
            resource="m1-local",
            operations=["text_to_speech"],
        )
    )
    for domain, model_flag, model_name in (
        ("voice", "tts", "Qwen3-TTS"),
        ("music", "music", "ACE-Step-1.5"),
        # Stable Audio is a review-pool capability, never a final route.
        ("music", "ambient", "Stable Audio Open 1.0"),
    ):
        ready = bool(audio_node.get("ok") and audio_models.get(model_flag))
        capabilities.append(
            _capability(
                capability_id=f"rtx5090-{domain}-{model_flag}",
                provider="private-audio-node",
                model=model_name,
                domains=[domain],
                status="ready" if ready else "blocked",
                # Service health is not an audio acceptance canary.
                pilot_verified=False,
                resource="gpu:rtx5090-audio",
                operations=["text_to_speech"] if domain == "voice" else ["text_to_video"],
            )
        )

    lipsync = probe_lipsync()
    node = lipsync.get("node") if isinstance(lipsync.get("node"), dict) else {}
    backend_rows = node.get("backends") if isinstance(node.get("backends"), dict) else {}
    for backend_id, backend in backend_rows.items():
        if not isinstance(backend, dict):
            continue
        ready = bool(backend.get("ready"))
        capabilities.append(
            _capability(
                capability_id=f"rtx5090-lipsync-{backend_id}",
                provider="private-lipsync-node",
                model=str(backend.get("model") or backend_id),
                domains=["lipsync"],
                status="ready" if ready else "blocked",
                pilot_verified=ready and backend.get("approved") is True,
                resource="gpu:rtx5090-lipsync",
                operations=["video_lip_sync"],
            )
        )
    observations["rtx5090_lipsync"] = {
        "ok": bool(node.get("ok")),
        "ready": lipsync.get("ready") or [],
    }

    # Grok is the declared dialogue secondary route.  A no-root provider probe
    # only proves that the in-session path exists; per-film canary evidence is
    # still required before it can become the active route.
    from i2v_provider import GrokI2VProvider

    grok = GrokI2VProvider().probe()
    grok_available = bool(grok.ok and grok.available)
    capabilities.append(
        _capability(
            capability_id="grok-imagine-video",
            provider="grok",
            model="grok-imagine-video",
            domains=["motion"],
            status="ready" if grok_available else "blocked",
            pilot_verified=False,
            resource="grok-in-session",
            operations=["image_to_video"],
            cost_state="unknown",
        )
    )
    observations["grok_imagine_video"] = {
        "available": grok_available,
        "reason": grok.reason,
        "film_canary_required": True,
    }

    post = probe_designed_post_tooling()
    ffmpeg_ready = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    story_available = False
    story_verified = False
    story_model = "local-llm-unconfigured"
    story_observation: dict[str, Any] = {"configured": False, "verified": False}
    story_base_url = os.environ.get("AIFILM_LOCAL_LLM_BASE_URL", "").strip()
    if story_base_url:
        story_observation["configured"] = True
        try:
            from local_llm import DEFAULT_MODEL, LocalLLMError, shot_draft
            from local_llm import probe as probe_local_llm

            token = os.environ.get("AIFILM_LOCAL_LLM_TOKEN") or None
            local_probe = probe_local_llm(story_base_url, token=token)
            story_available = local_probe.get("ok") is True
            story_model = str(local_probe.get("model") or DEFAULT_MODEL)
            if verify_story and story_available:
                canary = shot_draft(
                    story_base_url,
                    token=token,
                    prompt=(
                        "Return two concise safe film-shot candidates as JSON. "
                        "Shot one: a courier notices rain. Shot two: the courier protects a parcel."
                    ),
                )
                story_verified = canary.get("status") == "candidate_only"
            story_observation.update({"available": story_available, "verified": story_verified})
        except LocalLLMError as exc:
            story_observation.update({"available": False, "error": exc.code})
        except Exception as exc:
            story_observation.update({"available": False, "error": type(exc).__name__})
    capabilities.extend(
        [
            _capability(
                capability_id="m1-ffmpeg-quality",
                provider="m1-local",
                model="ffmpeg+ffprobe",
                domains=["qa"],
                status="ready" if ffmpeg_ready else "blocked",
                pilot_verified=ffmpeg_ready,
                resource="m1-local",
            ),
            _capability(
                capability_id="m1-hyperframes-post",
                provider="m1-local",
                model="HyperFrames",
                domains=["post"],
                status="ready" if post.get("hyperframes_ok") else "blocked",
                pilot_verified=False,
                resource="m1-local",
            ),
            _capability(
                capability_id="m1-story-reasoning",
                provider="m1-local",
                model=story_model,
                domains=["story"],
                status="ready" if story_available else "blocked",
                # A models-list response is not enough to bless story advice.
                pilot_verified=story_verified,
                resource="m1-local",
            ),
        ]
    )
    observations["m1"] = {
        "ffmpeg_quality": ffmpeg_ready,
        "hyperframes": bool(post.get("hyperframes_ok")),
        "story_model": story_observation,
    }
    snapshot = {
        "schema_version": 1,
        "kind": "ai-film-capability-snapshot",
        "generated_at": datetime.now(UTC).isoformat(),
        "capabilities": capabilities,
    }
    _validate_snapshot(snapshot)
    write_json(destination, snapshot)
    return {
        "ok": True,
        "written": str(destination),
        "snapshot": snapshot,
        "observations": observations,
    }


def _snapshot(path: Path | str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(path).expanduser().resolve()
    value = read_json(candidate)
    if not isinstance(value, dict):
        raise ProductionTeamError(f"CAPABILITY_SNAPSHOT_MISSING: {candidate}")
    try:
        _validate_snapshot(value)
    except RouteExplainError as exc:
        raise ProductionTeamError(str(exc)) from exc
    return candidate, value


def scaffold_team(
    root: Path | str,
    *,
    capabilities_path: Path | str,
    out: Path | str | None = None,
) -> dict[str, Any]:
    """Write a no-execution team plan with one named accountable director per craft."""
    base = Path(root).expanduser().resolve()
    snapshot_path, snapshot = _snapshot(capabilities_path)
    destination = Path(out).expanduser().resolve() if out else base / "production-team.json"
    capabilities = snapshot["capabilities"]
    assignments = [
        {
            "director_id": director["id"],
            "model_capability_ids": [],
            "local_tools": [],
            "human_review_required": True,
        }
        for director in DIRECTORS
    ]
    plan: dict[str, Any] = {
        "schema_version": TEAM_VERSION,
        "kind": "ai-film-production-team",
        "created_at": utc_now(),
        "root": str(base),
        "capability_snapshot": {"path": str(snapshot_path), "sha256": sha256_file(snapshot_path)},
        "directors": list(DIRECTORS),
        "assignments": assignments,
        "available_capabilities": [
            {key: item[key] for key in ("id", "provider", "model", "resource", "status")}
            for item in capabilities
        ],
        "auto_execute": False,
        "notes": [
            "Assign only pilot-verified, currently ready model capability IDs.",
            "M1 and LAN 5090 tools must be named explicitly; a declared local tool is not readiness proof.",
            "Each specialist advises and validates; human approval remains required at lock and spend boundaries.",
        ],
    }
    plan["content_sha256"] = canonical_json_sha256(plan)
    write_json(destination, plan)
    return {"ok": True, "written": str(destination), "plan": plan}


def validate_team(
    plan_path: Path | str,
    *,
    capabilities_path: Path | str,
    stage: str | None = None,
) -> dict[str, Any]:
    """Fail closed when a specialist lacks an owner or references stale model evidence."""
    plan_file = Path(plan_path).expanduser().resolve()
    plan = read_json(plan_file)
    if not isinstance(plan, dict) or plan.get("kind") != "ai-film-production-team":
        raise ProductionTeamError(f"TEAM_PLAN_MISSING_OR_INVALID: {plan_file}")
    recorded_hash = plan.get("content_sha256")
    unsigned = {key: value for key, value in plan.items() if key != "content_sha256"}
    if recorded_hash != canonical_json_sha256(unsigned):
        raise ProductionTeamError("TEAM_PLAN_HASH_MISMATCH")
    snapshot_path, snapshot = _snapshot(capabilities_path)
    snapshot_ref = (
        plan.get("capability_snapshot") if isinstance(plan.get("capability_snapshot"), dict) else {}
    )
    blockers: list[str] = []
    if snapshot_ref.get("sha256") != sha256_file(snapshot_path):
        blockers.append("CAPABILITY_SNAPSHOT_CHANGED")
    normalized_stage = str(stage or "").strip() or None
    if normalized_stage is not None and normalized_stage not in STAGE_DIRECTORS:
        raise ProductionTeamError(f"UNKNOWN_PRODUCTION_STAGE: {normalized_stage}")
    required_directors = (
        set(STAGE_DIRECTORS[normalized_stage]) if normalized_stage else _DIRECTOR_IDS
    )
    assignments = plan.get("assignments")
    if not isinstance(assignments, list):
        raise ProductionTeamError("TEAM_ASSIGNMENTS_INVALID")
    by_director: dict[str, dict[str, Any]] = {}
    for item in assignments:
        if not isinstance(item, dict):
            blockers.append("TEAM_ASSIGNMENT_INVALID")
            continue
        director_id = str(item.get("director_id") or "")
        if director_id not in _DIRECTOR_IDS or director_id in by_director:
            blockers.append("DIRECTOR_ASSIGNMENT_INVALID")
            continue
        by_director[director_id] = item
    capabilities = {str(item["id"]): item for item in snapshot["capabilities"]}
    coverage: list[dict[str, Any]] = []
    for director in DIRECTORS:
        director_id = director["id"]
        required = director_id in required_directors
        assignment = by_director.get(director_id)
        if assignment is None:
            coverage.append(
                {
                    "director_id": director_id,
                    "required": required,
                    "ok": not required,
                    "blockers": ["DIRECTOR_UNASSIGNED"] if required else [],
                }
            )
            if required:
                blockers.append(f"DIRECTOR_UNASSIGNED:{director_id}")
            continue
        capability_ids = assignment.get("model_capability_ids")
        local_tools = assignment.get("local_tools")
        if not isinstance(capability_ids, list) or not isinstance(local_tools, list):
            coverage.append(
                {
                    "director_id": director_id,
                    "required": required,
                    "ok": not required,
                    "blockers": ["ASSIGNMENT_FIELDS_INVALID"] if required else [],
                }
            )
            if required:
                blockers.append(f"ASSIGNMENT_FIELDS_INVALID:{director_id}")
            continue
        if not required:
            coverage.append(
                {"director_id": director_id, "required": False, "ok": True, "blockers": []}
            )
            continue
        reasons: list[str] = []
        if not capability_ids:
            reasons.append("NO_MODEL_ASSIGNED")
        supported_domains = set(director["domains"])
        for capability_id in capability_ids:
            capability = capabilities.get(str(capability_id))
            if capability is None:
                reasons.append(f"CAPABILITY_UNKNOWN:{capability_id}")
            elif (
                capability.get("status") != "ready" or capability.get("pilot_verified") is not True
            ):
                reasons.append(f"CAPABILITY_NOT_READY:{capability_id}")
            elif capability.get("experimental") is True:
                reasons.append(f"EXPERIMENTAL_CAPABILITY:{capability_id}")
            elif (
                isinstance(capability.get("domains"), list)
                and capability["domains"]
                and not (supported_domains & set(str(item) for item in capability["domains"]))
            ):
                reasons.append(f"CAPABILITY_DOMAIN_MISMATCH:{capability_id}")
        coverage.append(
            {"director_id": director_id, "required": True, "ok": not reasons, "blockers": reasons}
        )
        blockers.extend(f"{reason}:{director_id}" for reason in reasons)
    blockers = sorted(set(blockers))
    return {
        "ok": not blockers,
        "kind": "ai-film-production-team-validation",
        "read_only": True,
        "auto_execute": False,
        "plan": str(plan_file),
        "capability_snapshot": str(snapshot_path),
        "stage": normalized_stage,
        "required_directors": sorted(required_directors),
        "coverage": coverage,
        "blockers": blockers,
    }
