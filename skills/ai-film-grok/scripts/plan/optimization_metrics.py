"""Read-only aggregation of film receipts into a versioned optimisation vector."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from director_review import SCORECARD_DIMENSIONS
from generation_usage import usage_list, usage_status
from optimization_taxonomy import UNCLASSIFIED, normalize_code
from pipeline_events import load_events
from util import canonical_json_sha256, read_json, sha256_file, write_json

METRICS_VERSION = 2
PREMIUM_CROSSWALK = {
    "narrative_rhythm": "rhythm",
    "identity_continuity": "identity",
    "performance": "performance",
    "cinematography": "style",
    "motion_credibility": "motion",
    "sound": "audio",
    "caption_readability": "subs",
}


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _plugin_version() -> str | None:
    for parent in Path(__file__).resolve().parents:
        manifest = parent / "plugin.json"
        if not manifest.is_file():
            continue
        value = read_json(manifest)
        if isinstance(value, dict) and str(value.get("version") or "").strip():
            return str(value["version"])
    return None


def _load(base: Path, relative: str, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    path = base / relative
    if not path.is_file():
        sources.append({"path": relative, "state": "unknown"})
        return None
    try:
        value = read_json(path)
        sources.append(
            {
                "path": relative,
                "state": "known" if value is not None else "invalid",
                "sha256": sha256_file(path),
            }
        )
        return value
    except OSError:
        sources.append({"path": relative, "state": "invalid"})
        return None


def _quantiles(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"state": "unknown", "count": 0, "p10": None, "p50": None, "iqr": None}
    ordered = sorted(values)

    def q(fraction: float) -> float:
        index = (len(ordered) - 1) * fraction
        lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    return {
        "state": "known",
        "count": len(ordered),
        "p10": round(q(0.1), 4),
        "p50": round(q(0.5), 4),
        "iqr": round(q(0.75) - q(0.25), 4),
    }


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_from_manifest(manifest: dict[str, Any]) -> float | None:
    record = (
        (manifest.get("outputs") or {}).get("final_film")
        if isinstance(manifest.get("outputs"), dict)
        else None
    )
    if isinstance(record, dict):
        value = record.get("duration_sec")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _review_l2(review: dict[str, Any] | None, premium: dict[str, Any] | None) -> dict[str, Any]:
    dimensions: dict[str, Any] = {
        dim: {"pass": None, "grade": None, "fail_reason": []} for dim in SCORECARD_DIMENSIONS
    }
    if isinstance(review, dict):
        card = review.get("scorecard") if isinstance(review.get("scorecard"), dict) else {}
        flags = card.get("dimensions") if isinstance(card.get("dimensions"), dict) else {}
        grades = review.get("grades") if isinstance(review.get("grades"), dict) else {}
        reasons = review.get("fail_reasons") if isinstance(review.get("fail_reasons"), dict) else {}
        for dim in SCORECARD_DIMENSIONS:
            dimensions[dim] = {
                "pass": flags.get(dim) if isinstance(flags.get(dim), bool) else None,
                "grade": grades.get(dim) if isinstance(grades.get(dim), int) else None,
                "fail_reason": reasons.get(dim, []),
            }
    fail_counts: Counter[str] = Counter()
    grade_values: list[float] = []
    for value in dimensions.values():
        for code in value["fail_reason"] if isinstance(value["fail_reason"], list) else []:
            fail_counts[str(code)] += 1
        if isinstance(value["grade"], int):
            grade_values.append(float(value["grade"]))
    premium_scores = {}
    if isinstance(premium, dict):
        for item in premium.get("reviews") or []:
            if isinstance(item, dict) and isinstance(item.get("scores"), dict):
                for key, value in item["scores"].items():
                    if isinstance(value, int):
                        premium_scores.setdefault(key, []).append(value)
    return {
        "state": "known" if isinstance(review, dict) else "unknown",
        "approved": bool(review and review.get("approved")),
        "dimensions": dimensions,
        "grade_summary": _quantiles(grade_values),
        "fail_reasons": dict(sorted(fail_counts.items())),
        "premium_benchmark": {
            "state": "known" if premium_scores else "unknown",
            "source": "blind-review",
            "crosswalk": PREMIUM_CROSSWALK,
            "scores": {
                key: _quantiles([float(v) for v in values])
                for key, values in premium_scores.items()
            },
        },
    }


def emit_metrics(root: Path | str, *, run_id: str = "default") -> dict[str, Any]:
    base = _root(root)
    sources: list[dict[str, Any]] = []
    manifest = _load(base, "manifest.json", sources) or {}
    _load(base, "film-spec.json", sources)
    queue = _load(base, "receipts/media-queue.json", sources) or {}
    _load(base, "receipts/dailies.json", sources)
    review = _load(base, "out/final-review.json", sources)
    if review is None:
        review = _load(base, "out/final-review-failed.json", sources)
    premium = _load(base, "receipts/blind-review.json", sources)
    events, event_invalid = load_events(base)
    sources.append(
        {
            "path": "receipts/pipeline-events.jsonl",
            "state": "invalid" if event_invalid else ("known" if events else "unknown"),
        }
    )
    usage = usage_status(base)
    records = usage_list(base).get("records") or []
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    qa_values: list[float] = []
    motion_fail = 0
    clip_count = 0
    l0_errors: list[str] = []
    for shot_id, clip in clips.items():
        if not isinstance(clip, dict):
            continue
        clip_count += 1
        qa = clip.get("qa") if isinstance(clip.get("qa"), dict) else {}
        if qa.get("ok") is False:
            l0_errors.extend(str(item) for item in qa.get("errors") or [])
        motion = qa.get("motion_score")
        if isinstance(motion, (int, float)):
            qa_values.append(float(motion))
        if qa.get("motion_ok") is False:
            motion_fail += 1
    gates = manifest.get("gates") if isinstance(manifest.get("gates"), dict) else {}
    boolean_gates = [value for value in gates.values() if isinstance(value, bool)]
    l0 = {
        "state": "known" if manifest else "unknown",
        "hard_gates": gates,
        "all_pass": bool(boolean_gates) and all(boolean_gates),
        "final_complete": bool(gates.get("final_complete")),
        "clip_count": clip_count,
        "errors": l0_errors,
        "failed_gate_count": sum(1 for value in gates.values() if value is False),
    }
    l1 = {
        "state": "known" if clip_count else "unknown",
        "motion_score": _quantiles(qa_values),
        "motion_fail_rate": round(motion_fail / clip_count, 4) if clip_count else None,
        "per_shot": {
            str(sid): {
                "motion_score": (record.get("qa") or {}).get("motion_score"),
                "qa_ok": (record.get("qa") or {}).get("ok"),
            }
            for sid, record in clips.items()
            if isinstance(record, dict)
        },
    }
    l2 = _review_l2(review, premium)
    starts = [
        _parse_time(item.get("occurred_at"))
        for item in events
        if item.get("stage") == "init" and item.get("phase") == "completed"
    ]
    finals = [
        _parse_time(item.get("occurred_at"))
        for item in events
        if item.get("stage") == "review-final" and item.get("phase") == "completed"
    ]
    wall = (
        (finals[-1] - starts[0]).total_seconds()
        if starts and finals and starts[0] and finals[-1]
        else None
    )
    i2v: list[float] = []
    claimed: dict[str, datetime] = {}
    registered_events: list[dict[str, Any]] = []
    for item in events:
        if item.get("shot_id") and item.get("stage") == "i2v":
            timestamp = _parse_time(item.get("occurred_at"))
            if timestamp and item.get("phase") == "claimed":
                claimed[str(item["shot_id"])] = timestamp
            if item.get("phase") == "registered":
                registered_events.append(item)
                if timestamp and str(item["shot_id"]) in claimed:
                    i2v.append((timestamp - claimed[str(item["shot_id"])]).total_seconds())
    human_events = [item for item in events if item.get("phase") == "human_time"]
    human = sum(float(item.get("human_minutes") or 0) for item in human_events)
    errors = [
        str((item.get("error") or {}).get("code") or UNCLASSIFIED)
        for item in events
        if item.get("phase") == "failed"
    ]
    errors.extend(normalize_code(item) for item in l0_errors)
    final_duration = _duration_from_manifest(manifest)
    i2v_records = [record for record in records if record.get("operation") == "i2v"]
    i2v_cost_known = bool(i2v_records) and all(
        record.get("measurement") in {"provider_exact", "manual_exact", "local_zero"}
        and "cost_in_usd_ticks"
        in (record.get("usage") if isinstance(record.get("usage"), dict) else {})
        for record in i2v_records
    )
    all_cost_known = bool(records) and usage.get("unknown_cost_requests", 0) == 0
    cost_known = all_cost_known and (not clip_count or i2v_cost_known)
    cost = usage.get("cost_usd") if cost_known else None
    registered_shots = {
        str(item.get("shot_id"))
        for item in registered_events
        if str(item.get("shot_id") or "").strip()
    }
    registered_count = len(registered_events)
    approved_count = sum(
        1 for item in clips.values() if isinstance(item, dict) and item.get("status") == "approved"
    )
    jobs = queue.get("jobs") if isinstance(queue.get("jobs"), list) else []
    retry_count = (
        sum(
            max(0, int(record.get("attempts") or 1) - 1)
            for record in jobs
            if isinstance(record, dict)
        )
        if jobs
        else None
    )
    l3 = {
        "state": "known" if events or records else "unknown",
        "wall_sec_init_to_verified": wall,
        "sec_per_shot_i2v": _quantiles(i2v),
        "human_minutes": human if human_events else None,
        "human_time_state": "known" if human_events else "unknown",
        "retry_count": retry_count,
        "registered_event_count": registered_count,
        "unique_registered_shots": len(registered_shots),
        "registration_rework_count": max(0, registered_count - len(registered_shots)),
        "generation_usage": usage,
        "cost_usd": cost,
        "i2v_cost_state": "known" if i2v_cost_known else "unknown",
        "usd_per_pass_min": round(float(cost) / (final_duration / 60), 6)
        if cost is not None and final_duration and l2.get("approved")
        else None,
        "stage_yield": round(min(approved_count, registered_count) / registered_count, 4)
        if registered_count
        else None,
    }
    missing_evidence: list[str] = []
    if clip_count and not i2v:
        missing_evidence.append("i2v_timing")
    if clip_count and not i2v_cost_known:
        missing_evidence.append("i2v_cost")
    if (review or finals) and not human_events:
        missing_evidence.append("human_time")
    funnel = {
        "queued": len(jobs),
        "registered_clips": clip_count,
        "final_complete": bool(gates.get("final_complete")),
        "review_approved": l2.get("approved"),
    }
    report = {
        "schema_version": METRICS_VERSION,
        "kind": "optimization-metrics",
        "metadata": {
            "run_id": run_id,
            "film_root": str(base),
            "film_spec_sha256": sha256_file(base / "film-spec.json")
            if (base / "film-spec.json").is_file()
            else None,
            "final_output_sha256": ((manifest.get("outputs") or {}).get("final_film") or {}).get(
                "sha256"
            ),
            "plugin_version": _plugin_version(),
        },
        "data_quality": {
            "state": (
                "invalid"
                if event_invalid
                else ("partial" if missing_evidence else ("known" if manifest else "unknown"))
            ),
            "sources": sources,
            "invalid_events": event_invalid,
            "missing_evidence": missing_evidence,
        },
        "l0": l0,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "funnel": funnel,
        "error_pareto": dict(Counter(errors).most_common()),
    }
    stable = {key: value for key, value in report.items() if key != "content_sha256"}
    report["content_sha256"] = canonical_json_sha256(stable)
    write_json(base / "receipts" / "metrics.json", report)
    return report
