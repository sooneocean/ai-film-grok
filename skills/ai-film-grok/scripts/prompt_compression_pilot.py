"""Evidence ledger for prompt-compression Pilots; it never edits production prompts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pilot_review import pilot_scorecard_ready, user_phrase_is_approval
from prompt_budget import _line_kind
from security_policy import safe_existing_file
from util import read_json, write_json


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _receipt_path(root: Path, shot_id: str) -> Path:
    return root / "receipts" / f"prompt_assembly_{shot_id}.json"


def build_prompt_compression_pilot(root: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Bind source/candidate prompts while refusing to weaken protected locks."""
    root = Path(root).expanduser().resolve()
    source_line = str(candidate.get("source_line") or "").strip()
    shots = candidate.get("shots")
    if not source_line or _line_kind(source_line) != "review_before_removal":
        raise ValueError("source_line must be a review_before_removal compression candidate")
    if not isinstance(shots, list) or not shots:
        raise ValueError("candidate must contain at least one shot")

    bindings = []
    for item in shots:
        if not isinstance(item, dict):
            raise ValueError("candidate shots must be objects")
        shot_id = str(item.get("shot_id") or "").strip()
        candidate_prompt = str(item.get("candidate_prompt_text") or "").strip()
        if not shot_id or not candidate_prompt:
            raise ValueError("each candidate shot needs shot_id and candidate_prompt_text")
        receipt_path = _receipt_path(root, shot_id)
        receipt = read_json(receipt_path) or {}
        source_prompt = str(receipt.get("prompt_text") or "")
        if not source_prompt:
            raise ValueError(f"missing source prompt receipt for shot {shot_id}")
        source_lines = [line.strip() for line in source_prompt.splitlines() if line.strip()]
        candidate_lines = [line.strip() for line in candidate_prompt.splitlines() if line.strip()]
        if source_line not in source_lines or source_line in candidate_lines:
            raise ValueError(
                f"candidate for {shot_id} must remove exactly the declared source_line"
            )
        protected = [line for line in source_lines if _line_kind(line) != "review_before_removal"]
        missing_protected = [line for line in protected if line not in candidate_lines]
        if missing_protected:
            raise ValueError(f"candidate for {shot_id} removes protected prompt locks")
        bindings.append(
            {
                "shot_id": shot_id,
                "source_receipt": str(receipt_path),
                "source_prompt_hash": str(receipt.get("prompt_hash") or _sha256(source_prompt)),
                "candidate_prompt_hash": _sha256(candidate_prompt),
                "protected_lines_verified": protected,
                "estimated_input_tokens_before": (len(source_prompt) + 3) // 4,
                "estimated_input_tokens_candidate": (len(candidate_prompt) + 3) // 4,
            }
        )
    candidate_id = str(candidate.get("candidate_id") or _sha256(source_line)[:12])
    report = {
        "ok": True,
        "kind": "prompt-compression-pilot",
        "schema_version": 1,
        "candidate_id": candidate_id,
        "state": "needs_pilot_evidence",
        "source_line": source_line,
        "bindings": bindings,
        "estimated_input_tokens_saved": sum(
            item["estimated_input_tokens_before"] - item["estimated_input_tokens_candidate"]
            for item in bindings
        ),
        "required_evidence": [
            "same-condition candidate keyframe and clip for every bound shot",
            "candidate frame/continuity QA",
            "director scorecard and explicit human Pilot approval",
        ],
        "production_mutation": False,
        "approval": "not_granted",
    }
    path = root / "receipts" / "prompt-compression-pilot.json"
    write_json(path, report)
    report["path"] = str(path)
    return report


def attest_prompt_compression_pilot(
    root: Path, evidence: dict[str, Any], *, user_phrase: str
) -> dict[str, Any]:
    """Attach real Pilot evidence, but never promote a compression rule automatically."""
    root = Path(root).expanduser().resolve()
    ledger_path = root / "receipts" / "prompt-compression-pilot.json"
    ledger = read_json(ledger_path) or {}
    if ledger.get("kind") != "prompt-compression-pilot":
        raise ValueError("prompt-compression-pilot ledger is missing")
    if ledger.get("state") != "needs_pilot_evidence":
        raise ValueError("prompt-compression-pilot ledger is not awaiting evidence")
    if not user_phrase_is_approval(user_phrase):
        raise ValueError("attestation requires an explicit human Pilot approval phrase")
    if str(evidence.get("candidate_id") or "") != str(ledger.get("candidate_id") or ""):
        raise ValueError("evidence candidate_id does not match the Pilot ledger")

    scorecard = read_json(root / "receipts" / "pilot-scorecard.json")
    approval = read_json(root / "receipts" / "pilot-approval.json")
    if not pilot_scorecard_ready(scorecard):
        raise ValueError("attestation requires an all-pass pilot-scorecard")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise ValueError("attestation requires a recorded pilot-approval")

    evidence_shots = evidence.get("shots")
    if not isinstance(evidence_shots, list):
        raise ValueError("evidence must provide a shots list")
    by_shot = {str(item.get("shot_id")): item for item in evidence_shots if isinstance(item, dict)}
    bindings = ledger.get("bindings") if isinstance(ledger.get("bindings"), list) else []
    required_shots = [str(item.get("shot_id")) for item in bindings]
    if not set(required_shots).issubset(set(scorecard.get("shots") or [])):
        raise ValueError("pilot-scorecard does not cover every compression Pilot shot")
    if not set(required_shots).issubset(set(approval.get("shots") or [])):
        raise ValueError("pilot-approval does not cover every compression Pilot shot")

    verified = []
    for binding in bindings:
        shot_id = str(binding.get("shot_id"))
        item = by_shot.get(shot_id) or {}
        if item.get("candidate_prompt_hash") != binding.get("candidate_prompt_hash"):
            raise ValueError(f"candidate prompt hash mismatch for {shot_id}")
        artifacts = {}
        for field in ("keyframe_path", "clip_path", "frame_qa_path"):
            value = item.get(field)
            if not value:
                raise ValueError(f"evidence for {shot_id} is missing {field}")
            artifacts[field] = str(safe_existing_file(root, str(value), field=field))
        verified.append(
            {
                "shot_id": shot_id,
                "candidate_prompt_hash": binding["candidate_prompt_hash"],
                "artifacts": artifacts,
            }
        )

    attestation = {
        "kind": "prompt-compression-pilot-attestation",
        "schema_version": 1,
        "candidate_id": ledger["candidate_id"],
        "ledger_path": str(ledger_path),
        "user_phrase": user_phrase.strip(),
        "scorecard_path": str(root / "receipts" / "pilot-scorecard.json"),
        "approval_path": str(root / "receipts" / "pilot-approval.json"),
        "verified_shots": verified,
        "state": "evidence_complete_not_promoted",
        "promotion": "A separate director decision must promote any compression rule.",
    }
    attestation_path = root / "receipts" / "prompt-compression-pilot-attestation.json"
    write_json(attestation_path, attestation)
    ledger["state"] = "evidence_complete_not_promoted"
    ledger["attestation_path"] = str(attestation_path)
    ledger["approval"] = "human_pilot_approved_not_promoted"
    write_json(ledger_path, ledger)
    attestation["path"] = str(attestation_path)
    return attestation
