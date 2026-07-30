#!/usr/bin/env python3
"""Single post-production handoff contract for editorial and render engines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

POST_PLAN_NAME = "post-plan.json"
POST_PLAN_VERSION = 1
OWNERS = frozenset({"ffmpeg", "hyperframes", "remotion"})
SOURCE_TYPES = frozenset({"generated_clip", "real_footage"})


class PostPlanError(ValueError):
    """A post plan is missing a decision needed for a safe render."""


def post_plan_path(root: Path) -> Path:
    return root.expanduser().resolve() / POST_PLAN_NAME


def _relative_path(root: Path, value: str, *, field: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PostPlanError(f"{field} must be a workspace-relative path: {value!r}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PostPlanError(f"{field} escapes workspace: {value!r}") from exc
    return path.as_posix()


def _runtime_relative_path(root: Path, value: str, *, field: str) -> str:
    """Accept a trusted command result, but only when it remains inside the film root."""
    path = Path(value)
    if not path.is_absolute():
        return _relative_path(root, value, field=field)
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise PostPlanError(f"{field} escapes workspace: {value!r}") from exc


def _source_types_from_edl(root: Path, edl_path: str | None) -> list[str]:
    if not edl_path:
        return ["generated_clip"]
    edl = read_json(root / edl_path)
    if not edl:
        return ["generated_clip"]
    kinds: set[str] = set()
    default = str(edl.get("source_type") or "generated_clip")
    for item in edl.get("ranges") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("source_type") or default)
        kinds.add("generated_clip" if kind == "generated" else kind)
    return sorted(kinds or {"generated_clip"})


def new_post_plan(
    root: Path,
    *,
    owner: str = "hyperframes",
    edl_path: str | None = None,
    master_subtitles: str | None = "out/final.srt",
    audio_plan: str | None = "sound-plan.json",
) -> dict[str, Any]:
    """Build a deliberately small, inspectable post-production handoff."""
    root = root.expanduser().resolve()
    owner = owner.strip().lower()
    if owner not in OWNERS:
        raise PostPlanError(f"post_owner must be one of {sorted(OWNERS)}")
    if edl_path:
        edl_path = _relative_path(root, edl_path, field="editorial.edl")
    if master_subtitles:
        master_subtitles = _relative_path(
            root, master_subtitles, field="artifacts.master_subtitles"
        )
    if audio_plan:
        audio_plan = _relative_path(root, audio_plan, field="artifacts.audio_plan")
    return {
        "version": POST_PLAN_VERSION,
        "created_at": utc_now(),
        "post_owner": owner,
        "caption_owner": owner,
        "editorial": {
            "edl": edl_path,
            "source_types": _source_types_from_edl(root, edl_path),
            "rules": {
                "subtitles_last": True,
                "word_boundary_cuts": True,
                "segment_audio_fades_ms": 30,
            },
        },
        "artifacts": {
            "master_subtitles": master_subtitles,
            "audio_plan": audio_plan,
        },
        "render": {"engine": owner, "comparison_engine": None, "segment_limit_sec": 90},
        "acceptance": {
            "composition_check": False,
            "rendered_media": False,
            "ffprobe_readback": False,
            "technical_qa_report": None,
            "human_review": False,
        },
    }


def validate_post_plan(
    root: Path,
    plan: dict[str, Any],
    *,
    check_artifacts: bool = False,
) -> dict[str, Any]:
    """Validate the contract without pretending that a human has approved it."""
    root = root.expanduser().resolve()
    issues: list[str] = []
    if not isinstance(plan, dict):
        return {"ok": False, "issues": ["post-plan must be a JSON object"], "post_owner": None}
    if plan.get("version") != POST_PLAN_VERSION:
        issues.append(f"version must be {POST_PLAN_VERSION}")
    owner = plan.get("post_owner")
    if owner not in OWNERS:
        issues.append(f"post_owner must be one of {sorted(OWNERS)}")
    if plan.get("caption_owner") != owner:
        issues.append("caption_owner must equal post_owner; captions are burned exactly once")
    render = plan.get("render") if isinstance(plan.get("render"), dict) else {}
    if render.get("engine") != owner:
        issues.append("render.engine must equal post_owner")
    comparison = render.get("comparison_engine")
    if comparison is not None and comparison not in OWNERS - {owner}:
        issues.append("render.comparison_engine must name the other engine or be null")
    editorial = plan.get("editorial") if isinstance(plan.get("editorial"), dict) else {}
    source_types = editorial.get("source_types")
    if not isinstance(source_types, list) or not source_types:
        issues.append("editorial.source_types must be a non-empty list")
    elif any(value not in SOURCE_TYPES for value in source_types):
        issues.append(f"editorial.source_types must use {sorted(SOURCE_TYPES)}")
    rules = editorial.get("rules") if isinstance(editorial.get("rules"), dict) else {}
    if rules.get("subtitles_last") is not True:
        issues.append("editorial.rules.subtitles_last must be true")
    if rules.get("word_boundary_cuts") is not True:
        issues.append("editorial.rules.word_boundary_cuts must be true")
    if rules.get("segment_audio_fades_ms") != 30:
        issues.append("editorial.rules.segment_audio_fades_ms must be 30")
    for field, value in {
        "editorial.edl": editorial.get("edl"),
        "artifacts.master_subtitles": (plan.get("artifacts") or {}).get("master_subtitles"),
        "artifacts.audio_plan": (plan.get("artifacts") or {}).get("audio_plan"),
    }.items():
        if value is None:
            continue
        if not isinstance(value, str):
            issues.append(f"{field} must be a relative path or null")
            continue
        try:
            relative = _relative_path(root, value, field=field)
        except PostPlanError as exc:
            issues.append(str(exc))
            continue
        if check_artifacts and not (root / relative).is_file():
            issues.append(f"{field} is missing: {relative}")
    acceptance = plan.get("acceptance")
    if not isinstance(acceptance, dict):
        issues.append("acceptance must be an object")
    else:
        for name in ("composition_check", "rendered_media", "ffprobe_readback", "human_review"):
            if not isinstance(acceptance.get(name), bool):
                issues.append(f"acceptance.{name} must be boolean")
        if acceptance.get("human_review") is True:
            issues.append("acceptance.human_review is recorded by review-final, never post-plan")
        if acceptance.get("ffprobe_readback") is True:
            report = acceptance.get("technical_qa_report")
            if not isinstance(report, str):
                issues.append("acceptance.ffprobe_readback requires technical_qa_report")
            else:
                try:
                    relative = _relative_path(root, report, field="acceptance.technical_qa_report")
                    receipt = read_json(root / relative)
                    if not receipt or not bool((receipt.get("technical_qa") or {}).get("ok")):
                        issues.append("acceptance.technical_qa_report lacks passing technical_qa")
                except PostPlanError as exc:
                    issues.append(str(exc))
    return {"ok": not issues, "issues": issues, "post_owner": owner}


def load_post_plan(root: Path, *, required: bool = False) -> dict[str, Any] | None:
    path = post_plan_path(root)
    data = read_json(path)
    if data is None:
        if required:
            raise PostPlanError(f"Missing {path.name}; run: aifilm post-plan --root … init")
        return None
    result = validate_post_plan(root, data)
    if not result["ok"]:
        raise PostPlanError(f"Invalid {path.name}: {'; '.join(result['issues'])}")
    return data


def write_post_plan(root: Path, plan: dict[str, Any], *, force: bool = False) -> Path:
    path = post_plan_path(root)
    if path.exists() and not force:
        raise PostPlanError(f"{path.name} exists; pass --force to replace it")
    result = validate_post_plan(root, plan)
    if not result["ok"]:
        raise PostPlanError(f"Invalid {path.name}: {'; '.join(result['issues'])}")
    write_json(path, plan)
    return path


def ensure_post_plan(root: Path, *, owner: str) -> tuple[dict[str, Any], bool]:
    """Create the default handoff once; an existing owner is never overwritten."""
    root = root.expanduser().resolve()
    existing = load_post_plan(root)
    if existing is not None:
        return existing, False
    edl = "edit/edl.json" if (root / "edit" / "edl.json").is_file() else None
    plan = new_post_plan(root, owner=owner, edl_path=edl)
    write_post_plan(root, plan)
    return plan, True


def validate_render_owner(root: Path, engine: str) -> dict[str, Any] | None:
    """Honor an existing plan while retaining backward compatibility for old films."""
    plan = load_post_plan(root)
    if plan is None:
        return None
    owner = str(plan["post_owner"])
    if engine not in {owner, "both"}:
        raise PostPlanError(
            f"post-plan post_owner={owner}; use --engine {owner} (or both for comparison)"
        )
    if engine == "both" and owner != "hyperframes":
        raise PostPlanError(
            "engine=both renders HyperFrames as final; post-plan owner must be hyperframes"
        )
    return plan


def record_render_evidence(
    root: Path,
    *,
    engine: str,
    output: str | None,
    composition_checked: bool = False,
    ffprobe_readback: bool = False,
    technical_qa_report: str | None = None,
) -> None:
    """Record technical completion only; human_review remains an explicit later gate."""
    root = root.expanduser().resolve()
    plan = load_post_plan(root)
    if plan is None:
        return
    if engine != plan["post_owner"]:
        return
    acceptance = plan["acceptance"]
    acceptance["composition_check"] = bool(acceptance["composition_check"] or composition_checked)
    acceptance["rendered_media"] = bool(acceptance["rendered_media"] or output)
    acceptance["ffprobe_readback"] = bool(acceptance["ffprobe_readback"] or ffprobe_readback)
    if ffprobe_readback:
        if not technical_qa_report:
            raise PostPlanError("ffprobe evidence requires a final-delivery technical_qa report")
        acceptance["technical_qa_report"] = _runtime_relative_path(
            root, technical_qa_report, field="acceptance.technical_qa_report"
        )
    plan["last_rendered_at"] = utc_now()
    write_json(post_plan_path(root), plan)


def delivery_status(root: Path, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read the formal final/review records; never infer human approval from this plan."""
    root = root.expanduser().resolve()
    if plan is None:
        try:
            plan = load_post_plan(root, required=True)
        except PostPlanError as exc:
            return {"present": post_plan_path(root).is_file(), "ok": False, "error": str(exc)}
    manifest = read_json(root / "manifest.json") or {}
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    final = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    review = outputs.get("final_review") if isinstance(outputs.get("final_review"), dict) else {}
    final_engine = final.get("post_engine")
    owner_matches = bool(final_engine and final_engine == plan["post_owner"])
    review_matches = bool(
        review.get("approved") is True
        and final.get("sha256")
        and review.get("output_sha256") == final.get("sha256")
    )
    acceptance = plan["acceptance"]
    technical_ready = bool(
        acceptance.get("rendered_media")
        and acceptance.get("ffprobe_readback")
        and acceptance.get("technical_qa_report")
    )
    return {
        "present": True,
        "ok": True,
        "post_owner": plan["post_owner"],
        "final_engine": final_engine,
        "owner_matches_final": owner_matches,
        "technical_ready": technical_ready,
        "human_reviewed": review_matches,
        "release_ready": bool(owner_matches and technical_ready and review_matches),
    }
