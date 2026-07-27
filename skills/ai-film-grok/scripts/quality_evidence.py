"""One hash-bound quality receipt for every approved motion clip.

The receipt does not replace the existing media QA, review, or uniqueness
records.  It binds their successful results to the exact media that was
reviewed, so a later replacement cannot inherit an old approval.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from security_policy import validate_identifier
from util import read_json, sha256_file, utc_now, write_json


class QualityEvidenceError(ValueError):
    """A clip lacks evidence required for an approved delivery path."""


def evidence_path(root: Path | str, shot_id: str) -> Path:
    sid = validate_identifier(str(shot_id), field="shot id")
    return Path(root).expanduser().resolve() / "receipts" / "quality-evidence" / f"{sid}.json"


def _require(value: bool, message: str) -> None:
    if not value:
        raise QualityEvidenceError(message)


def _review_binding(review: dict[str, Any] | None) -> dict[str, str]:
    _require(isinstance(review, dict), "approved clip requires hash-bound human review evidence")
    raw_path = review.get("path")
    _require(isinstance(raw_path, str) and raw_path.strip(), "human review receipt path is missing")
    path = Path(raw_path).expanduser().resolve()
    _require(path.is_file(), "human review receipt is missing")
    actual = sha256_file(path)
    expected = review.get("sha256")
    _require(expected in {None, actual}, "human review receipt hash does not match")
    receipt = read_json(path)
    _require(receipt.get("approved") is True, "human review receipt is not approved")
    continuity = receipt.get("continuity_packet")
    _require(
        isinstance(continuity, dict) and continuity.get("ok") is True,
        "continuity review is missing",
    )
    return {"path": str(path), "sha256": actual}


def build_shot_quality_evidence(
    root: Path | str,
    *,
    shot_id: str,
    clip: Path | str,
    qa: dict[str, Any],
    source_endpoint: str | None,
    identity_approved: bool,
    motion_approved: bool,
    review: dict[str, Any] | None,
    uniqueness: dict[str, Any] | None,
    continuity: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a fail-closed receipt from successful existing quality gates."""
    sid = validate_identifier(str(shot_id), field="shot id")
    source = Path(clip).expanduser().resolve()
    _require(source.is_file() and source.stat().st_size > 0, "approved clip media is missing")
    _require(
        isinstance(qa, dict) and qa.get("ok") is True, "approved clip requires passing motion QA"
    )
    _require(
        qa.get("decode_ok") is True and qa.get("motion_ok") is True,
        "approved clip requires decode and real motion",
    )
    _require(bool(source_endpoint), "approved clip source endpoint is missing")
    _require(identity_approved, "approved clip requires identity approval")
    _require(motion_approved, "approved clip requires human motion approval")
    _require(
        isinstance(uniqueness, dict) and bool(uniqueness.get("sha256")),
        "approved clip requires a visual fingerprint",
    )
    clip_hash = sha256_file(source)
    _require(
        str(uniqueness.get("sha256")) == clip_hash,
        "clip fingerprint does not match the approved media",
    )
    review_binding = _review_binding(review)
    _require(
        isinstance(continuity, dict) and continuity.get("ok") is True,
        "continuity review is not approved",
    )
    _require(isinstance(provider, dict), "approved clip requires provider receipt")
    _require(provider.get("ok") is True, "provider receipt is not successful")
    _require(provider.get("output_sha256") == clip_hash, "provider receipt does not match clip")

    evidence = {
        "schema_version": 1,
        "kind": "shot-quality-evidence",
        "ok": True,
        "created_at": utc_now(),
        "shot_id": sid,
        "clip": {"path": str(source), "sha256": clip_hash, "bytes": source.stat().st_size},
        "technical_qa": qa,
        "source_endpoint": source_endpoint,
        "approvals": {"identity": True, "motion": True},
        "review": review_binding,
        "uniqueness": uniqueness,
        "continuity": continuity,
        "provider": provider,
    }
    path = evidence_path(root, sid)
    write_json(path, evidence)
    evidence["path"] = str(path)
    evidence["sha256"] = sha256_file(path)
    return evidence


def quality_evidence_is_current(evidence: object, *, clip: Path | str) -> bool:
    if not isinstance(evidence, dict) or evidence.get("kind") != "shot-quality-evidence":
        return False
    source = Path(clip).expanduser().resolve()
    record = evidence.get("clip") if isinstance(evidence.get("clip"), dict) else {}
    if not (
        evidence.get("ok") is True
        and source.is_file()
        and record.get("sha256") == sha256_file(source)
        and Path(str(record.get("path") or "")).expanduser().resolve() == source
    ):
        return False
    review = evidence.get("review") if isinstance(evidence.get("review"), dict) else {}
    path = Path(str(review.get("path") or "")).expanduser()
    if not path.is_file() or review.get("sha256") != sha256_file(path):
        return False
    receipt = read_json(path)
    continuity = receipt.get("continuity_packet") if isinstance(receipt, dict) else {}
    if not (
        receipt.get("approved") is True
        and continuity.get("ok") is True
        and continuity.get("reviewed_clip_sha256") == record.get("sha256")
    ):
        return False
    neighbours = continuity.get("neighbours") if isinstance(continuity, dict) else {}
    if not isinstance(neighbours, dict):
        return False
    for item in neighbours.values():
        if not isinstance(item, dict):
            return False
        neighbour = Path(str(item.get("clip_path") or "")).expanduser()
        if not neighbour.is_file() or item.get("clip_sha256") != sha256_file(neighbour):
            return False
    return True


def load_current_quality_evidence(
    root: Path | str, *, shot_id: str, clip: Path | str
) -> dict[str, Any]:
    evidence = read_json(evidence_path(root, shot_id))
    if not quality_evidence_is_current(evidence, clip=clip):
        raise QualityEvidenceError(
            "shot quality evidence is missing, stale, or bound to another clip"
        )
    return evidence
