"""Evidence contracts for challenger promotion and cost-aware production stages."""

from __future__ import annotations

import math
import subprocess
from collections.abc import Iterable
from pathlib import Path
from statistics import median
from typing import Any

from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

PROGRAM_VERSION = 1
PROGRAM_PATH = "receipts/optimization-program.json"
STAGE_PATH = "receipts/optimization-stages.json"
AUDIO_PATH = "receipts/optimization-audio.json"

CHALLENGERS = {
    "infinitetalk": {
        "role": "lipsync",
        "allowed_stage": "formal",
        "requires": ["face_visible", "locked_final_dialogue", "human_lipsync_review"],
    },
    "ltx-fast": {
        "role": "draft_motion",
        "allowed_stage": "draft",
        "requires": ["no_identity_promotion", "still_approved", "motion_review"],
    },
    "hunyuan-720p-sr": {
        "role": "formal_upscale",
        "allowed_stage": "formal",
        "requires": ["720p_decode", "sr_artifact_review", "human_visual_review"],
    },
    "realesrgan-animevideo": {
        "role": "formal_upscale",
        "allowed_stage": "formal",
        "requires": [
            "selects_or_preferred",
            "source_media_hash",
            "sr_artifact_review",
            "temporal_consistency_review",
            "human_visual_review",
            "no_auto_promotion",
        ],
    },
}

AUDIO_LANES = {
    "qwen3-tts": "dialogue_or_narration",
    "ace-step": "instrumental_bgm",
    "stable-audio": "ambience_candidate",
    "mmaudio": "video_conditioned_foley",
}

WEEKLY_METRICS = (
    "hard_gate_pass_rate",
    "review_approved_rate",
    "grade_p50",
    "motion_p10",
    "motion_fail_rate",
    "stage_yield",
    "usd_per_pass_min",
    "i2v_sec_p50",
    "retry_count",
    "human_minutes",
)


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _path(root: Path | str, relative: str) -> Path:
    return _root(root) / relative


def _write_bound(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    stable = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = canonical_json_sha256(stable)
    write_json(path, payload)
    return payload


def _read_or_empty(root: Path | str, relative: str, *, kind: str) -> dict[str, Any]:
    value = read_json(_path(root, relative))
    if value is None:
        return {"schema_version": PROGRAM_VERSION, "kind": kind, "items": []}
    if not isinstance(value, dict) or value.get("kind") != kind:
        raise ValueError(f"invalid {kind} receipt")
    digest = value.get("content_sha256")
    stable = {key: item for key, item in value.items() if key != "content_sha256"}
    if not isinstance(digest, str) or digest != canonical_json_sha256(stable):
        raise ValueError(f"tampered {kind} receipt")
    return value


def init_program(root: Path | str) -> dict[str, Any]:
    """Create the no-spend program contract; preserve an existing contract."""
    path = _path(root, PROGRAM_PATH)
    existing = read_json(path)
    if existing is not None:
        return _read_or_empty(root, PROGRAM_PATH, kind="optimization-program")
    return _write_bound(
        path,
        {
            "schema_version": PROGRAM_VERSION,
            "kind": "optimization-program",
            "created_at": utc_now(),
            "challengers": {
                key: {**value, "status": "research"} for key, value in CHALLENGERS.items()
            },
            "two_stage_policy": {
                "draft_requires": [
                    "still_approved",
                    "composition_pass",
                    "motion_pass",
                    "continuity_pass",
                ],
                "formal_requires_passing_draft": True,
                "bad_still_starts_video": False,
                "automatic_provider_dispatch": False,
            },
            "weekly_metrics": list(WEEKLY_METRICS),
            "audio_lanes": {
                key: {"role": value, "status": "research"} for key, value in AUDIO_LANES.items()
            },
            "post_policy": {
                "allowed_owners": ["hyperframes", "remotion"],
                "ffmpeg_role": "assembly_mix_encode",
                "single_post_owner_required": True,
                "burn_captions_once": True,
            },
            "default_route_changed": False,
        },
    )


def record_draft_stage(
    root: Path | str,
    *,
    shot_id: str,
    model: str,
    still_approved: bool,
    composition_pass: bool,
    motion_pass: bool,
    continuity_pass: bool,
) -> dict[str, Any]:
    if not shot_id.strip() or model not in CHALLENGERS:
        raise ValueError("shot_id and a known challenger model are required")
    if CHALLENGERS[model]["allowed_stage"] != "draft":
        raise ValueError(f"{model} is not a draft-stage model")
    receipt = _read_or_empty(root, STAGE_PATH, kind="optimization-stages")
    item = {
        "shot_id": shot_id,
        "stage": "draft",
        "model": model,
        "still_approved": still_approved,
        "composition_pass": composition_pass,
        "motion_pass": motion_pass,
        "continuity_pass": continuity_pass,
        "passed": all((still_approved, composition_pass, motion_pass, continuity_pass)),
        "recorded_at": utc_now(),
        "automatic_provider_dispatch": False,
    }
    receipt["items"].append(item)
    _write_bound(_path(root, STAGE_PATH), receipt)
    return item


def approve_formal_stage(
    root: Path | str, *, shot_id: str, formal_model: str, evidence_receipt: Path | str
) -> dict[str, Any]:
    if formal_model not in CHALLENGERS or CHALLENGERS[formal_model]["allowed_stage"] != "formal":
        raise ValueError("formal_model must be a known formal-stage challenger")
    receipt = _read_or_empty(root, STAGE_PATH, kind="optimization-stages")
    draft = next(
        (
            item
            for item in reversed(receipt["items"])
            if item.get("shot_id") == shot_id and item.get("stage") == "draft"
        ),
        None,
    )
    if not isinstance(draft, dict) or not draft.get("passed"):
        raise ValueError("formal stage requires a passing draft receipt")
    evidence_path = Path(evidence_receipt).expanduser().resolve()
    evidence = read_json(evidence_path) if evidence_path.is_file() else None
    required = CHALLENGERS[formal_model]["requires"]
    missing = [
        key for key in required if not isinstance(evidence, dict) or evidence.get(key) is not True
    ]
    if not isinstance(evidence, dict) or not str(evidence.get("reviewer") or "").strip():
        missing.append("reviewer")
    if missing:
        raise ValueError(f"formal {formal_model} requires: {', '.join(missing)}")
    item = {
        "shot_id": shot_id,
        "stage": "formal_authorized",
        "model": formal_model,
        "draft_receipt_sha256": canonical_json_sha256(draft),
        "evidence_receipt_sha256": sha256_file(evidence_path),
        "recorded_at": utc_now(),
        "automatic_provider_dispatch": False,
        "changes_default_route": False,
    }
    receipt["items"].append(item)
    _write_bound(_path(root, STAGE_PATH), receipt)
    return item


def record_audio_lane(
    root: Path | str,
    *,
    lane: str,
    artifact: Path | str,
    review_receipt: Path | str,
    production_eligible: bool,
) -> dict[str, Any]:
    if lane not in AUDIO_LANES:
        raise ValueError("unknown audio lane")
    artifact_path = Path(artifact).expanduser().resolve()
    review_path = Path(review_receipt).expanduser().resolve()
    if not artifact_path.is_file() or not review_path.is_file():
        raise ValueError("artifact and review_receipt must be existing files")
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", str(artifact_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("artifact ffprobe timed out") from exc
    if probe.returncode != 0:
        raise ValueError("artifact fails ffprobe read-back")
    review = read_json(review_path)
    artifact_sha = sha256_file(artifact_path)
    if (
        not isinstance(review, dict)
        or review.get("human_reviewed") is not True
        or review.get("artifact_sha256") != artifact_sha
        or not str(review.get("reviewer") or "").strip()
    ):
        raise ValueError("review_receipt requires human_reviewed=true and reviewer")
    if lane in {"stable-audio", "mmaudio"} and production_eligible:
        raise ValueError(f"{lane} remains a review-gated candidate lane")
    receipt = _read_or_empty(root, AUDIO_PATH, kind="optimization-audio")
    item = {
        "lane": lane,
        "artifact_sha256": artifact_sha,
        "artifact": str(artifact_path),
        "review_receipt_sha256": sha256_file(review_path),
        "decoded": True,
        "human_reviewed": True,
        "production_eligible": production_eligible,
        "status": "reviewed_candidate" if not production_eligible else "reviewed_eligible",
        "recorded_at": utc_now(),
    }
    receipt["items"].append(item)
    _write_bound(_path(root, AUDIO_PATH), receipt)
    return item


def _number(report: dict[str, Any], *path: str) -> float | None:
    value: Any = report
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return float(value) if type(value) in {int, float} and math.isfinite(float(value)) else None


def _aggregate(values: list[float]) -> float | None:
    return round(float(median(values)), 4) if values else None


def weekly_summary(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    all_reports = list(reports)
    known = [
        report for report in all_reports if report.get("data_quality", {}).get("state") == "known"
    ]
    maps = {
        "grade_p50": ("l2", "grade_summary", "p50"),
        "motion_p10": ("l1", "motion_score", "p10"),
        "motion_fail_rate": ("l1", "motion_fail_rate"),
        "stage_yield": ("l3", "stage_yield"),
        "usd_per_pass_min": ("l3", "usd_per_pass_min"),
        "i2v_sec_p50": ("l3", "sec_per_shot_i2v", "p50"),
        "retry_count": ("l3", "retry_count"),
        "human_minutes": ("l3", "human_minutes"),
    }
    metrics: dict[str, dict[str, Any]] = {}
    for name, path in maps.items():
        values = [value for report in known if (value := _number(report, *path)) is not None]
        metrics[name] = {"value": _aggregate(values), "sample_count": len(values)}
    for name, path in (
        ("hard_gate_pass_rate", ("l0", "all_pass")),
        ("review_approved_rate", ("l2", "approved")),
    ):
        values = [report.get(path[0], {}).get(path[1]) for report in known]
        numeric = [float(value) for value in values if type(value) is bool]
        metrics[name] = {
            "value": round(sum(numeric) / len(numeric), 4) if numeric else None,
            "sample_count": len(numeric),
        }
    return {
        "kind": "optimization-weekly-summary",
        "data_quality": "known"
        if known and len(known) == len(all_reports)
        else ("partial" if known else "unknown"),
        "run_count": len(known),
        "metrics": {name: metrics[name] for name in WEEKLY_METRICS},
    }


def _bound_metrics(report: dict[str, Any], challenger: str | None = None) -> bool:
    digest = report.get("content_sha256")
    return (
        report.get("kind") == "optimization-metrics"
        and (challenger is None or report.get("metadata", {}).get("challenger") == challenger)
        and isinstance(digest, str)
        and digest
        == canonical_json_sha256(
            {key: value for key, value in report.items() if key != "content_sha256"}
        )
    )


def evaluate_challenger(
    root: Path | str,
    *,
    challenger: str,
    reports: list[dict[str, Any]],
    baseline_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    if challenger not in CHALLENGERS:
        raise ValueError("unknown challenger")
    if len(reports) < 3 or len(reports) != len(baseline_reports):
        raise ValueError("challenger evaluation requires three complete projects")
    roots = [str(report.get("metadata", {}).get("film_root") or "") for report in reports]
    baseline_roots = [
        str(report.get("metadata", {}).get("film_root") or "") for report in baseline_reports
    ]
    if (
        len(set(roots)) != len(roots)
        or len(set(baseline_roots)) != len(baseline_roots)
        or set(roots) & set(baseline_roots)
        or any(not root for root in roots + baseline_roots)
        or not all(_bound_metrics(report, challenger) for report in reports)
        or not all(_bound_metrics(report) for report in baseline_reports)
    ):
        raise ValueError("challenger reports must be distinct checksum-bound projects")
    complete = [
        report
        for report in reports
        if report.get("data_quality", {}).get("state") == "known"
        and report.get("l0", {}).get("all_pass") is True
        and report.get("l2", {}).get("approved") is True
    ]
    if len(complete) < 3:
        raise ValueError("three complete known non-regressing projects are required")
    for candidate, baseline in zip(reports, baseline_reports, strict=True):
        if not (
            baseline.get("data_quality", {}).get("state") == "known"
            and baseline.get("l0", {}).get("all_pass") is True
            and baseline.get("l2", {}).get("approved") is True
        ):
            raise ValueError("baseline must be complete and approved")
        for path, lower_is_better in (
            (("l2", "grade_summary", "p50"), False),
            (("l1", "motion_score", "p10"), False),
            (("l1", "motion_fail_rate"), True),
            (("l3", "usd_per_pass_min"), True),
            (("l3", "sec_per_shot_i2v", "p50"), True),
            (("l3", "retry_count"), True),
            (("l3", "human_minutes"), True),
        ):
            after, before = _number(candidate, *path), _number(baseline, *path)
            if (
                after is None
                or before is None
                or (after > before if lower_is_better else after < before)
            ):
                raise ValueError("challenger has incomplete or regressing baseline evidence")
    summary = weekly_summary(complete)
    result = {
        "kind": "challenger-evaluation",
        "challenger": challenger,
        "evaluated_at": utc_now(),
        "complete_projects": len(complete),
        "weekly_summary": summary,
        "recommendation": "request_human_promotion",
        "automatic_promotion": False,
        "changes_default_route": False,
    }
    path = _path(root, "receipts/challenger-evaluations.json")
    receipt = _read_or_empty(
        root, "receipts/challenger-evaluations.json", kind="challenger-evaluations"
    )
    receipt["items"].append(result)
    _write_bound(path, receipt)
    return result
