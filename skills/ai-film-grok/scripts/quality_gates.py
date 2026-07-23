"""Quality evidence and promotion gates for generated stills and clips.

The technical media probe answers whether a file is usable.  This module adds
the production question: is this take safe to promote for its shot role?
Hero shots are intentionally stricter than environment/bridge inserts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from continuity_chain import load_frame_chain_receipt
from media_qa import analyze_still_geometry
from util import read_json, sha256_file, write_json

HERO_FUNCTIONS = frozenset({"hero", "action", "continue", "climax", "union", "rhythm"})
_ARTIFACT_TEXT = re.compile(
    r"(?:\bshot\s*\d{1,3}\b|\bkeyframe(?:[-_ ]?v?\d+)\b|\bcast\s+master\s+v\d+\b|\bversion\s*\d+)",
    re.IGNORECASE,
)


class QualityGateError(ValueError):
    """A still or clip cannot be promoted as a quality-approved take."""


def _shot(root: Path, shot_id: str) -> dict[str, Any]:
    spec = read_json(root / "film-spec.json") or {}
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and str(shot.get("id")) == str(shot_id):
                return shot
    return {}


def shot_role(root: Path, shot_id: str) -> str:
    shot = _shot(root, shot_id)
    role = str(shot.get("shot_role") or "").strip().lower()
    if role in {"env", "bridge", "insert", "background"}:
        return "environment"
    function = str(shot.get("dramatic_function") or "").strip().lower()
    if role in HERO_FUNCTIONS or function in HERO_FUNCTIONS:
        return "hero"
    # A-roll is the safe default when a legacy spec has no shot_role.
    return "hero"


def _style_evidence(root: Path) -> dict[str, Any]:
    style = read_json(root / "style-bible.json") or {}
    cast = style.get("cast_masters") if isinstance(style.get("cast_masters"), dict) else {}
    return {
        "locked": style.get("locked") is True
        or str(style.get("state") or "").lower() == "approved",
        "canonical_style_path": style.get("canonical_style_path"),
        "cast_masters": cast,
    }


def _prompt_text_clean(prompt_file: Path | None) -> tuple[bool, list[str]]:
    if prompt_file is None or not prompt_file.is_file():
        return True, []
    text = prompt_file.read_text(encoding="utf-8", errors="replace")
    matches = sorted(set(match.group(0) for match in _ARTIFACT_TEXT.finditer(text)))
    return not matches, matches


def evaluate_keyframe(
    root: Path,
    *,
    shot_id: str,
    source: Path,
    aspect_ratio: str,
    prompt_file: Path | None,
    identity_approved: bool,
    review_note: str,
) -> dict[str, Any]:
    """Evaluate keyframe geometry, provenance and obvious prompt contamination."""
    role = shot_role(root, shot_id)
    geometry = analyze_still_geometry(source, aspect_ratio=aspect_ratio)
    style = _style_evidence(root)
    prompt_clean, artifact_tokens = _prompt_text_clean(prompt_file)
    errors = list(geometry.get("errors") or [])
    codes = list(geometry.get("codes") or [])
    warnings = list(geometry.get("soft") or [])
    if not prompt_clean:
        codes.append("KEYFRAME_PROMPT_ARTIFACT_TEXT")
        errors.append("prompt contains production artifact text: " + ", ".join(artifact_tokens))
    if role == "hero" and not identity_approved:
        codes.append("HERO_IDENTITY_REVIEW_MISSING")
        errors.append("hero keyframe requires identity approval against cast/state master")
    if role == "hero" and not style["locked"]:
        codes.append("HERO_STYLE_LOCK_MISSING")
        errors.append("hero keyframe requires a locked style bible")
    result = {
        "schema_version": 1,
        "kind": "keyframe-quality",
        "shot_id": str(shot_id),
        "role": role,
        "ok": not errors and bool(geometry.get("ok")),
        "hard": errors,
        "warnings": warnings,
        "codes": sorted(set(codes)),
        "geometry": geometry,
        "style": style,
        "prompt": {
            "path": str(prompt_file) if prompt_file else None,
            "sha256": sha256_file(prompt_file) if prompt_file and prompt_file.is_file() else None,
            "artifact_text_clean": prompt_clean,
            "artifact_tokens": artifact_tokens,
        },
        "source": {
            "path": str(source),
            "sha256": sha256_file(source) if source.is_file() else None,
        },
        "identity_approved": bool(identity_approved),
        "review_note": review_note,
    }
    return result


def evaluate_clip(
    root: Path,
    *,
    shot_id: str,
    qa: dict[str, Any],
    endpoint: str | None,
    identity_approved: bool,
    motion_approved: bool,
    review: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply the hero hard gate while keeping environment clips lightweight."""
    role = shot_role(root, shot_id)
    errors: list[str] = []
    codes: list[str] = []
    if not qa.get("ok"):
        errors.extend(str(item) for item in qa.get("errors") or ["technical media QA failed"])
        codes.append("TECHNICAL_MEDIA_QA_FAILED")
    if role == "environment":
        return {
            "schema_version": 1,
            "kind": "clip-quality",
            "shot_id": str(shot_id),
            "role": role,
            "ok": not errors,
            "hard": errors,
            "warnings": [],
            "codes": sorted(set(codes)),
            "endpoint": endpoint,
            "technical_qa": qa,
            "review": review,
        }
    if not identity_approved:
        errors.append("hero clip requires identity approval")
        codes.append("HERO_IDENTITY_REVIEW_MISSING")
    if not motion_approved:
        errors.append("hero clip requires full-clip motion approval")
        codes.append("HERO_MOTION_REVIEW_MISSING")
    if not isinstance(review, dict):
        errors.append("hero clip requires an approved shot-review receipt")
        codes.append("HERO_SHOT_REVIEW_MISSING")
    else:
        scores = review.get("scorecard") if isinstance(review.get("scorecard"), dict) else {}
        dimensions = scores.get("dimensions") if isinstance(scores.get("dimensions"), dict) else {}
        required = ("identity", "continuity", "composition", "motion", "narrative")
        weak = [name for name in required if int(dimensions.get(name) or 0) < 4]
        if weak:
            errors.append("hero shot-review score below 4: " + ", ".join(weak))
            codes.append("HERO_SHOT_REVIEW_SCORE_LOW")
        if review.get("approved") is False:
            errors.append("hero shot-review is not approved")
            codes.append("HERO_SHOT_REVIEW_NOT_APPROVED")
    # A continue join must already be byte-safe before the next clip is promoted.
    chain = load_frame_chain_receipt(root)
    joins = [j for j in chain.get("joins") or [] if isinstance(j, dict) and j.get("to") == shot_id]
    if joins and any(j.get("byte_identical") is not True for j in joins):
        errors.append("hero continue join is not byte-identical")
        codes.append("HERO_CONTINUITY_JOIN_FAILED")
    return {
        "schema_version": 1,
        "kind": "clip-quality",
        "shot_id": str(shot_id),
        "role": role,
        "ok": not errors,
        "hard": errors,
        "warnings": [],
        "codes": sorted(set(codes)),
        "endpoint": endpoint,
        "technical_qa": qa,
        "review": review,
        "continuity_joins_checked": len(joins),
    }


def write_quality_receipt(root: Path, shot_id: str, report: dict[str, Any]) -> Path:
    path = Path(root).expanduser().resolve() / "receipts" / "quality" / f"{shot_id}.json"
    write_json(path, report)
    return path


def require_quality(report: dict[str, Any], *, kind: str) -> None:
    if report.get("ok") is True:
        return
    details = "; ".join(str(item) for item in report.get("hard") or ["quality gate failed"])
    raise QualityGateError(f"{kind} quality gate failed: {details}")
