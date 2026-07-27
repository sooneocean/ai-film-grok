"""Evidence-bound premium quality closure without implicit provider spend.

Automated gates can establish that a film is structurally ready.  They cannot
truthfully certify artistic quality, which requires real provider media and
independent human review.  This module makes that boundary explicit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, sha256_file, write_json

BENCHMARK_VERSION = "premium-vertical-v1"
REVIEW_DIMENSIONS = (
    "narrative_rhythm",
    "identity_continuity",
    "performance",
    "cinematography",
    "motion_credibility",
    "sound",
    "caption_readability",
    "overall_completion",
)
DIMENSION_CODES = {
    "identity_continuity": "IDENTITY_CONTINUITY_LOW",
    "motion_credibility": "MOTION_CREDIBILITY_LOW",
    "narrative_rhythm": "NARRATIVE_RHYTHM_LOW",
    "caption_readability": "CAPTION_READABILITY_LOW",
    "sound": "SOUND_QUALITY_LOW",
    "performance": "PERFORMANCE_QUALITY_LOW",
    "cinematography": "CINEMATOGRAPHY_QUALITY_LOW",
    "overall_completion": "OVERALL_COMPLETION_LOW",
}
REPAIR_ACTIONS = {
    "IDENTITY_CONTINUITY_LOW": (
        "register-still",
        "aifilm register-still --root {root} --shot-id <shot-id> --image <approved-identity-still>",
        "身份/服装漂移：先重建并注册角色定妆 still，再重做受影响镜头。",
    ),
    "MOTION_CREDIBILITY_LOW": (
        "reshoot-motion",
        "aifilm dailies record --root {root} --shot-id <shot-id> --candidate <clip> --status reshoot --reviewer <reviewer>",
        "运动失真：回到 I2V 输入、首尾帧与镜头动作设计后重拍。",
    ),
    "NARRATIVE_RHYTHM_LOW": (
        "repair-rhythm",
        'aifilm plan edit --root {root} --instruction "tighten beats and EDL around the failed turn"',
        "节奏问题：回到 beats/EDL，先修叙事转折再重新剪辑。",
    ),
    "CAPTION_READABILITY_LOW": (
        "repair-captions",
        "aifilm final --root {root} --post-engine hyperframes",
        "字幕问题：只由当前 post engine 重烧并重新做 caption-frame attestation。",
    ),
    "SOUND_QUALITY_LOW": (
        "repair-sound",
        "aifilm post-quality audio-check --root {root}",
        "声音问题：回到混音与 stem，不以画面重渲染掩盖问题。",
    ),
    "PERFORMANCE_QUALITY_LOW": (
        "repair-performance",
        "aifilm review-shot --root {root} --shot-id <shot-id> --clip <clip>",
        "表演问题：先审片定位，再调整动作/对白/反应镜头后重拍。",
    ),
    "CINEMATOGRAPHY_QUALITY_LOW": (
        "repair-cinematography",
        "aifilm write-spec --root {root}",
        "构图问题：回到 shot DSL、framing 和 keyframe，而不是后期裁切补救。",
    ),
    "OVERALL_COMPLETION_LOW": (
        "repair-master",
        "aifilm post-audit --root {root}",
        "整体完成度不足：先以 post audit 汇总阻断项，再按最高严重度修复。",
    ),
}


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _receipt(root: Path, name: str) -> Path:
    return root / "receipts" / name


def _quality_target(root: Path) -> str:
    return str((read_json(root / "production-book.json") or {}).get("quality_target") or "standard")


def build_benchmark_package(root: Path | str) -> dict[str, Any]:
    """Write a fixed, no-spend premium benchmark brief bound to project truth."""
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    blockers: list[dict[str, str]] = []
    if _quality_target(base) != "premium_vertical":
        blockers.append(
            {"code": "QUALITY_TARGET_NOT_PREMIUM", "message": "set quality_target=premium_vertical"}
        )
    if str(spec.get("aspect") or spec.get("aspect_ratio") or "") not in {"9:16", ""}:
        blockers.append(
            {"code": "BENCHMARK_NOT_VERTICAL", "message": "benchmark requires 9:16 delivery"}
        )
    if not isinstance(spec.get("shots"), list):
        blockers.append(
            {"code": "BENCHMARK_SHOTS_MISSING", "message": "film-spec shots are required"}
        )
    report = {
        "schema_version": 1,
        "kind": "premium-vertical-benchmark-package",
        "benchmark_version": BENCHMARK_VERSION,
        "quality_target": _quality_target(base),
        "spend_authorized": False,
        "requirements": {
            "aspect_ratio": "9:16",
            "character_wardrobe_location_locks": True,
            "dialogue": True,
            "visible_action": True,
            "burned_captions": True,
            "bgm_and_mix": True,
            "continue_endpoint_match": True,
            "delivery_package": True,
        },
        "review_dimensions": list(REVIEW_DIMENSIONS),
        "shot_count": len(spec.get("shots") or []),
        "blockers": blockers,
        "ok": not blockers,
    }
    write_json(_receipt(base, "premium-benchmark-package.json"), report)
    return report


def _validate_scores(scores: dict[str, Any]) -> dict[str, int]:
    if set(scores) != set(REVIEW_DIMENSIONS):
        missing = sorted(set(REVIEW_DIMENSIONS) - set(scores))
        extra = sorted(set(scores) - set(REVIEW_DIMENSIONS))
        raise ValueError(
            f"scores must contain exactly review dimensions; missing={missing}, extra={extra}"
        )
    parsed: dict[str, int] = {}
    for dimension in REVIEW_DIMENSIONS:
        value = scores[dimension]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise ValueError(f"{dimension} score must be an integer from 1 to 5")
        parsed[dimension] = value
    return parsed


def _review_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    disagreements: list[dict[str, Any]] = []
    reshoot_queue: list[dict[str, str]] = []
    if len(reviews) >= 2:
        for dimension in REVIEW_DIMENSIONS:
            values = [int(review["scores"][dimension]) for review in reviews]
            if max(values) - min(values) >= 2:
                disagreements.append({"dimension": dimension, "scores": values})
            if min(values) <= 2:
                reshoot_queue.append(
                    {
                        "code": DIMENSION_CODES[dimension],
                        "dimension": dimension,
                        "severity": "blocker",
                    }
                )
    return {
        "review_count": len(reviews),
        "independent_review_complete": len(
            {str(r.get("reviewer_key") or str(r["reviewer"]).strip().casefold()) for r in reviews}
        )
        >= 2,
        "disagreements": disagreements,
        "reshoot_queue": reshoot_queue,
        "ok": len(reviews) >= 2 and not reshoot_queue,
    }


def record_blind_review(
    root: Path | str, *, reviewer: str, scores: dict[str, Any], notes: str
) -> dict[str, Any]:
    """Record one independent review; duplicate reviewers cannot self-confirm."""
    base = _root(root)
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    reviewer_key = reviewer.casefold()
    path = _receipt(base, "blind-review.json")
    ledger = read_json(path) or {"schema_version": 1, "kind": "blind-review", "reviews": []}
    reviews = ledger.setdefault("reviews", [])
    if any(
        str(item.get("reviewer_key") or str(item.get("reviewer") or "").strip().casefold())
        == reviewer_key
        for item in reviews
        if isinstance(item, dict)
    ):
        raise ValueError("reviewer already submitted a blind review")
    reviews.append(
        {
            "reviewer": reviewer,
            "reviewer_key": reviewer_key,
            "scores": _validate_scores(scores),
            "notes": notes.strip(),
        }
    )
    report = {**ledger, **_review_summary(reviews), "human_review_required": True}
    write_json(path, report)
    return report


def _has_real_provider_media(root: Path) -> bool:
    report = read_json(_receipt(root, "provider-canary.json")) or {}
    output = Path(str(report.get("output") or ""))
    if not output.is_absolute():
        output = root / output
    try:
        output_hash = sha256_file(output) if output.is_file() else None
    except OSError:
        output_hash = None
    if not (
        report.get("ok")
        and output_hash
        and output_hash == report.get("output_sha256")
        and report.get("human_review_required")
    ):
        return False
    provider = str(report.get("provider") or "")
    manifest = read_json(root / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    for record in clips.values():
        if not isinstance(record, dict):
            continue
        path = Path(str(record.get("path") or ""))
        if not path.is_absolute():
            path = root / path
        if (
            path.resolve(strict=False) != output.resolve(strict=False)
            or record.get("sha256") != output_hash
            or record.get("status") != "approved"
            or record.get("active") is not True
        ):
            continue
        try:
            from i2v_provider import for_endpoint

            owner = for_endpoint(str(record.get("source_endpoint") or ""))
        except (ImportError, ValueError):
            owner = None
        if owner is not None and owner.name == provider:
            return True
    return False


def _shot_quality_closure(root: Path) -> dict[str, Any]:
    """Validate every current-contract approved shot before master claims."""
    manifest = read_json(root / "manifest.json") or {}
    if int(manifest.get("quality_evidence_contract_version") or 0) < 1:
        return {"required": False, "ok": True, "missing": [], "duplicates": []}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    required = [
        str(sid)
        for sid, record in clips.items()
        if isinstance(record, dict) and record.get("status") == "approved"
    ]
    try:
        from clip_uniqueness import active_clip_reuse_report
        from quality_evidence import quality_evidence_is_current
    except ImportError:
        return {"required": True, "ok": False, "missing": required, "duplicates": []}
    missing: list[str] = []
    for shot_id in required:
        record = clips[shot_id]
        if not quality_evidence_is_current(
            record.get("quality_evidence"), clip=Path(str(record.get("path") or ""))
        ):
            missing.append(shot_id)
    uniqueness = active_clip_reuse_report(manifest, required_shot_ids=required)
    return {
        "required": True,
        "ok": not missing and uniqueness["ok"],
        "approved_shot_count": len(required),
        "missing": sorted(missing),
        "duplicates": uniqueness["duplicate_sha256_groups"],
        "missing_fingerprints": uniqueness["missing_fingerprint_shots"],
    }


def build_quality_report(root: Path | str) -> dict[str, Any]:
    """Summarize evidence without upgrading contract-only work into an art claim."""
    base = _root(root)
    package = read_json(_receipt(base, "premium-benchmark-package.json")) or {}
    review = read_json(_receipt(base, "blind-review.json")) or {}
    provider = read_json(_receipt(base, "provider-canary.json")) or {}
    post = read_json(_receipt(base, "premium-master-qc.json")) or {}
    delivery = read_json(_receipt(base, "premium-delivery-package.json")) or {}
    shot_quality = _shot_quality_closure(base)
    evidence = {
        "contract": {
            "present": bool(package.get("ok")),
            "receipt": "premium-benchmark-package.json",
        },
        "local_render": {
            "present": bool(post.get("final_sha256")),
            "receipt": "premium-master-qc.json",
        },
        "real_provider": {
            "present": _has_real_provider_media(base),
            "receipt": "provider-canary.json",
        },
        "human_reviewed": {
            "present": bool(review.get("independent_review_complete")),
            "receipt": "blind-review.json",
        },
        "shot_quality": shot_quality,
    }
    blocking_codes: list[str] = []
    if not evidence["contract"]["present"]:
        blocking_codes.append("BENCHMARK_CONTRACT_MISSING")
    if not evidence["real_provider"]["present"]:
        blocking_codes.append("REAL_PROVIDER_MEDIA_MISSING")
    if not evidence["human_reviewed"]["present"]:
        blocking_codes.append("INDEPENDENT_BLIND_REVIEW_MISSING")
    if not shot_quality["ok"]:
        blocking_codes.append("SHOT_QUALITY_EVIDENCE_MISSING")
    blocking_codes.extend(
        item["code"] for item in review.get("reshoot_queue", []) if item.get("code")
    )
    artistic = bool(
        not blocking_codes
        and post.get("ok") is True
        and delivery.get("ok") is True
        and review.get("ok") is True
    )
    report = {
        "schema_version": 1,
        "kind": "premium-quality-closure",
        "benchmark_version": BENCHMARK_VERSION,
        "evidence": evidence,
        "claims": {
            "quality_closure_ready": bool(evidence["contract"]["present"]),
            "artistic_quality_verified": artistic,
            "claim": "artistic quality is unverified"
            if not artistic
            else "artistic quality verified",
        },
        "review": review,
        "provider": {"provider": provider.get("provider"), "ok": provider.get("ok") is True},
        "blocking_codes": sorted(set(blocking_codes)),
        "ok": artistic,
    }
    write_json(_receipt(base, "premium-quality-report.json"), report)
    return report


def repair_action(root: Path | str) -> dict[str, Any] | None:
    """Return only the most severe, evidence-backed repair action."""
    base = _root(root)
    review = read_json(_receipt(base, "blind-review.json")) or {}
    queue = review.get("reshoot_queue") or []
    if not queue:
        return None
    priority = [
        "IDENTITY_CONTINUITY_LOW",
        "MOTION_CREDIBILITY_LOW",
        "NARRATIVE_RHYTHM_LOW",
        "CAPTION_READABILITY_LOW",
        "SOUND_QUALITY_LOW",
        "PERFORMANCE_QUALITY_LOW",
        "CINEMATOGRAPHY_QUALITY_LOW",
        "OVERALL_COMPLETION_LOW",
    ]
    codes = {str(item.get("code")) for item in queue if isinstance(item, dict)}
    code = next((item for item in priority if item in codes), None)
    if code is None:
        return None
    action_id, cmd, why = REPAIR_ACTIONS[code]
    return {
        "id": action_id,
        "code": code,
        "cmd": cmd.format(root=str(base)),
        "why": why,
        "stage": "visual"
        if code in {"IDENTITY_CONTINUITY_LOW", "MOTION_CREDIBILITY_LOW"}
        else "post",
        "evidence": {"kind": "blind-review", "receipt": str(_receipt(base, "blind-review.json"))},
    }
