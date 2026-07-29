"""Hash-bound JSON intake for the final director review."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from director_review import (
    SCORECARD_DIMENSIONS,
    DirectorReviewError,
    build_scorecard_from_mapping,
)
from security_policy import SecurityPolicyError, safe_existing_file
from util import canonical_json_sha256, read_json, utc_now, write_json

RECEIPT_NAME = "final-review-input.json"


class FinalReviewInputError(ValueError):
    pass


def _root(root: Path | str) -> Path:
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise FinalReviewInputError("film root must be an existing directory")
    return base


def review_input_template(root: Path | str) -> dict[str, Any]:
    base = _root(root)
    manifest = read_json(base / "manifest.json")
    if not isinstance(manifest, dict):
        raise FinalReviewInputError("manifest is missing")
    final = (manifest.get("outputs") or {}).get("final_film")
    if not isinstance(final, dict) or not str(final.get("sha256") or "").strip():
        raise FinalReviewInputError("current final film hash is missing")
    return {
        "schema_version": 1,
        "kind": "final-review-input-template",
        "final_output_sha256": str(final["sha256"]),
        "review_contract_version": int(manifest.get("review_contract_version") or 1),
        "dimensions": list(SCORECARD_DIMENSIONS),
    }


def _normalize_payload(root: Path, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FinalReviewInputError("final review input must be a JSON object")
    template = review_input_template(root)
    if raw.get("kind") != "final-review-input" or int(raw.get("schema_version") or 0) != 1:
        raise FinalReviewInputError("final review input kind/schema_version is invalid")
    if raw.get("approve") is not True:
        raise FinalReviewInputError("final review input requires approve=true")
    final_hash = str(raw.get("final_output_sha256") or "").strip()
    if final_hash != template["final_output_sha256"]:
        raise FinalReviewInputError("final review input does not match the current final output")
    reviewer = str(raw.get("reviewer") or "").strip()
    notes = str(raw.get("notes") or "").strip()
    if not reviewer or len(reviewer) > 80 or not notes:
        raise FinalReviewInputError("reviewer and notes are required")
    contract = int(template["review_contract_version"])
    watched_full = raw.get("watched_full") is True
    if contract >= 3 and not watched_full:
        raise FinalReviewInputError("review contract v3 requires watched_full=true")
    try:
        scorecard = build_scorecard_from_mapping(raw.get("scorecard"))
    except DirectorReviewError as exc:
        raise FinalReviewInputError(str(exc)) from exc
    grades_raw = raw.get("grades")
    if not isinstance(grades_raw, dict):
        grades_raw = {}
    grades: dict[str, int] = {}
    for dimension in SCORECARD_DIMENSIONS:
        value = grades_raw.get(dimension)
        if value is None and contract < 3:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise FinalReviewInputError(f"grade {dimension} must be an integer from 1 to 5")
        grades[dimension] = value
    evidence_raw = raw.get("screening_evidence")
    if not isinstance(evidence_raw, dict):
        evidence_raw = {}
    evidence: dict[str, dict[str, Any]] = {}
    for dimension in SCORECARD_DIMENSIONS:
        item = evidence_raw.get(dimension)
        if item is None and contract < 2:
            continue
        if not isinstance(item, dict):
            raise FinalReviewInputError(f"screening evidence missing dimension: {dimension}")
        timestamp = item.get("timestamp_sec")
        note = str(item.get("note") or "").strip()
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or float(timestamp) < 0
            or not note
        ):
            raise FinalReviewInputError(f"screening evidence is invalid for {dimension}")
        evidence[dimension] = {"timestamp_sec": float(timestamp), "note": note}
    failures = [dimension for dimension, passed in scorecard.items() if not passed]
    reasons_raw = raw.get("fail_reasons")
    if not isinstance(reasons_raw, dict):
        reasons_raw = {}
    fail_reasons: dict[str, list[str]] = {}
    for dimension in failures:
        values = reasons_raw.get(dimension)
        if not isinstance(values, list) or not all(str(value).strip() for value in values):
            if contract >= 3:
                raise FinalReviewInputError(f"fail reason missing dimension: {dimension}")
            continue
        fail_reasons[dimension] = [str(value).strip() for value in values]
    shots_raw = raw.get("reshoot_shots") or []
    if isinstance(shots_raw, str):
        shots = [value.strip() for value in shots_raw.split(",") if value.strip()]
    elif isinstance(shots_raw, list):
        shots = [str(value).strip() for value in shots_raw if str(value).strip()]
    else:
        raise FinalReviewInputError("reshoot_shots must be a list or comma-separated string")
    human_minutes = raw.get("human_minutes")
    if (
        isinstance(human_minutes, bool)
        or not isinstance(human_minutes, (int, float))
        or not 0 < float(human_minutes) <= 1440
    ):
        raise FinalReviewInputError("human_minutes must be > 0 and <= 1440")
    normalized = {
        "schema_version": 1,
        "kind": "final-review-input",
        "approve": True,
        "reviewer": reviewer,
        "notes": notes,
        "watched_full": watched_full,
        "final_output_sha256": final_hash,
        "human_minutes": round(float(human_minutes), 3),
        "scorecard": {
            dimension: "pass" if scorecard[dimension] else "fail"
            for dimension in SCORECARD_DIMENSIONS
        },
        "grades": grades,
        "screening_evidence": evidence,
        "fail_reasons": fail_reasons,
        "reshoot_shots": shots,
        "validated_at": utc_now(),
    }
    normalized["content_sha256"] = canonical_json_sha256(normalized)
    return normalized


def write_review_input(root: Path | str, raw: object) -> dict[str, Any]:
    base = _root(root)
    normalized = _normalize_payload(base, raw)
    target = base / "receipts" / RECEIPT_NAME
    write_json(target, normalized)
    return {
        "ok": True,
        "kind": "final-review-input-receipt",
        "path": str(target),
        "content_sha256": normalized["content_sha256"],
        "final_output_sha256": normalized["final_output_sha256"],
    }


def apply_review_input(args: Namespace, *, root: Path | str, path: Path | str) -> dict[str, Any]:
    base = _root(root)
    try:
        source = safe_existing_file(base, Path(path).expanduser(), field="final review input")
    except SecurityPolicyError as exc:
        raise FinalReviewInputError(str(exc)) from exc
    raw = read_json(source)
    normalized = _normalize_payload(base, raw)
    args.approve = True
    args.reviewer = normalized["reviewer"]
    args.notes = normalized["notes"]
    args.watched_full = normalized["watched_full"]
    args.reshoot_shots = ",".join(normalized["reshoot_shots"])
    args.screening_evidence = [
        f"{dimension}@{item['timestamp_sec']}:{item['note']}"
        for dimension, item in normalized["screening_evidence"].items()
    ]
    args.fail_reason = [
        f"{dimension}:{reason}"
        for dimension, reasons in normalized["fail_reasons"].items()
        for reason in reasons
    ]
    for dimension in SCORECARD_DIMENSIONS:
        setattr(args, f"score_{dimension}", normalized["scorecard"][dimension])
        setattr(args, f"grade_{dimension}", normalized["grades"].get(dimension))
    return normalized
