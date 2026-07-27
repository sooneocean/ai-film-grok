"""Personal, receipt-backed retrospective for one completed film.

This is deliberately a report and a human decision record. It never approves
media, starts a provider request, or turns an unknown provider cost into zero.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from generation_usage import usage_list
from optimization_metrics import emit_metrics
from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

SCHEMA_VERSION = 1
LEDGER_PATH = Path("receipts/quality-ledger.json")


class QualityLedgerError(ValueError):
    """A retrospective cannot be safely recorded."""


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _manual(existing: dict[str, Any] | None) -> dict[str, Any]:
    value = existing.get("manual") if isinstance(existing, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def _shot_rows(manifest: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    by_shot: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        shot_id = str(record.get("shot_id") or "").strip()
        if shot_id:
            by_shot.setdefault(shot_id, []).append(record)
    rows = []
    for shot_id in sorted(set(clips) | set(by_shot)):
        clip = clips.get(shot_id) if isinstance(clips.get(shot_id), dict) else {}
        qa = clip.get("qa") if isinstance(clip.get("qa"), dict) else {}
        quality = clip.get("quality_gate") if isinstance(clip.get("quality_gate"), dict) else {}
        attempts = by_shot.get(shot_id, [])
        known_ticks = 0
        unknown_cost = 0
        statuses: Counter[str] = Counter()
        for attempt in attempts:
            statuses[str(attempt.get("status") or "incomplete")] += 1
            usage = attempt.get("usage") if isinstance(attempt.get("usage"), dict) else {}
            measurement = str(attempt.get("measurement") or "unknown")
            if measurement in {"provider_exact", "manual_exact", "local_zero"} and (
                "cost_in_usd_ticks" in usage
            ):
                known_ticks += int(usage["cost_in_usd_ticks"])
            else:
                unknown_cost += 1
        rows.append(
            {
                "shot_id": shot_id,
                "generation": {
                    "attempt_count": len(attempts),
                    "status_counts": dict(sorted(statuses.items())),
                    "cost_in_usd_ticks": known_ticks if attempts and not unknown_cost else None,
                    "unknown_cost_attempts": unknown_cost,
                },
                "quality": {
                    "clip_status": clip.get("status"),
                    "identity_approved": clip.get("identity_approved"),
                    "motion_approved": clip.get("motion_approved"),
                    "motion_score": qa.get("motion_score"),
                    "media_qa_ok": qa.get("ok"),
                    "uniqueness_recorded": bool(
                        isinstance(clip.get("uniqueness"), dict)
                        and clip["uniqueness"].get("sha256")
                    ),
                    "shot_review_approved": bool(
                        isinstance(clip.get("shot_review"), dict)
                        and clip["shot_review"].get("approved") is True
                    ),
                    "quality_gate_ok": quality.get("ok"),
                },
            }
        )
    return rows


def _generation_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    """Make an incomplete provider bill explicit instead of displaying zero."""
    source = metrics.get("l3", {}).get("generation_usage", {})
    summary = dict(source) if isinstance(source, dict) else {}
    if int(summary.get("unknown_cost_requests") or 0) > 0:
        summary["cost_in_usd_ticks"] = None
        summary["cost_usd"] = None
        summary["cost_state"] = "unknown"
    else:
        summary["cost_state"] = "known"
    return summary


def emit_quality_ledger(root: Path | str) -> dict[str, Any]:
    """Refresh automatic evidence while retaining prior human conclusions."""
    base = _root(root)
    existing = read_json(base / LEDGER_PATH) or {}
    manifest = read_json(base / "manifest.json") or {}
    if not isinstance(manifest, dict):
        raise QualityLedgerError("manifest.json must be an object")
    metrics = emit_metrics(base)
    usage = usage_list(base)
    records = usage.get("records") if isinstance(usage.get("records"), list) else []
    review = (
        read_json(base / "out" / "final-review.json")
        or read_json(base / "out" / "final-review-failed.json")
        or {}
    )
    manual = _manual(existing)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "quality-ledger",
        "generated_at": utc_now(),
        "film_root": str(base),
        "sources": {
            "manifest_sha256": sha256_file(base / "manifest.json")
            if (base / "manifest.json").is_file()
            else None,
            "metrics_sha256": metrics.get("content_sha256"),
            "final_review_sha256": sha256_file(base / "out" / "final-review.json")
            if (base / "out" / "final-review.json").is_file()
            else None,
        },
        "delivery": {
            "final_complete": bool((manifest.get("gates") or {}).get("final_complete")),
            "review_approved": review.get("approved") is True,
            "review_grades": review.get("grades") if isinstance(review.get("grades"), dict) else {},
            "review_fail_reasons": review.get("fail_reasons")
            if isinstance(review.get("fail_reasons"), dict)
            else {},
        },
        "generation": _generation_summary(metrics),
        "quality": {
            "hard_gates": metrics.get("l0", {}).get("hard_gates", {}),
            "motion": metrics.get("l1", {}),
            "review": metrics.get("l2", {}),
            "error_pareto": metrics.get("error_pareto", {}),
        },
        "shots": _shot_rows(manifest, records),
        "manual": manual,
        "retrospective_complete": all(
            key in manual and manual[key] not in {None, ""}
            for key in ("director_score", "worth_publishing", "p0_improvement")
        ),
    }
    stable = {key: value for key, value in report.items() if key != "content_sha256"}
    report["content_sha256"] = canonical_json_sha256(stable)
    write_json(base / LEDGER_PATH, report)
    return report


def record_retrospective(
    root: Path | str,
    *,
    director_score: int,
    worth_publishing: bool,
    p0_improvement: str,
    reshoot_reasons: list[str],
) -> dict[str, Any]:
    if not 0 <= director_score <= 100:
        raise QualityLedgerError("director_score must be between 0 and 100")
    p0 = p0_improvement.strip()
    if not p0 or len(p0) > 280:
        raise QualityLedgerError("p0_improvement must be 1-280 characters")
    reasons = [item.strip() for item in reshoot_reasons if item.strip()]
    if any(len(item) > 280 for item in reasons):
        raise QualityLedgerError("each reshoot_reason must be at most 280 characters")
    report = emit_quality_ledger(root)
    delivery = report["delivery"]
    if not delivery["final_complete"] or not delivery["review_approved"]:
        raise QualityLedgerError(
            "retrospective requires an approved final_complete review; run review-final first"
        )
    report["manual"] = {
        "director_score": director_score,
        "worth_publishing": bool(worth_publishing),
        "p0_improvement": p0,
        "reshoot_reasons": reasons,
        "recorded_at": utc_now(),
    }
    report["retrospective_complete"] = True
    stable = {key: value for key, value in report.items() if key != "content_sha256"}
    report["content_sha256"] = canonical_json_sha256(stable)
    write_json(_root(root) / LEDGER_PATH, report)
    return report
