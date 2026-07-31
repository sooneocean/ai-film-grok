"""Read-only production evidence ledger for director and batch gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from narrative_control import control_status
from production_gates import pilot_is_user_approved
from util import read_json


def _present(root: Path, relative: str) -> bool:
    return (root / relative).is_file()


def _queue_contract_evidence(root: Path) -> dict[str, Any]:
    """Report whether queued work still matches the plan and assets it started with."""
    state = read_json(root / "receipts" / "media-queue.json") or {}
    jobs = state.get("jobs", []) if isinstance(state, dict) else []
    if not isinstance(jobs, list):
        return {"job_count": 0, "contracts_current": False, "chain_bound": False}
    checked = 0
    stale_job_ids: list[str] = []
    unbound_job_ids: list[str] = []
    from production_chain import queue_contract_is_current

    for job in jobs:
        if not isinstance(job, dict):
            continue
        contract = job.get("source_contract")
        job_id = str(job.get("id") or "unknown")
        if not isinstance(contract, dict):
            unbound_job_ids.append(job_id)
            continue
        checked += 1
        if not queue_contract_is_current(root, contract).get("ok"):
            stale_job_ids.append(job_id)
    return {
        "job_count": len(jobs),
        "checked_contracts": checked,
        "contracts_current": not stale_job_ids,
        "chain_bound": not unbound_job_ids,
        "stale_job_ids": stale_job_ids,
        "unbound_job_ids": unbound_job_ids,
    }


def build_evidence(root: Path) -> dict[str, Any]:
    control = control_status(root)
    pilot = read_json(root / "receipts" / "pilot-approval.json") or {}
    scorecard = read_json(root / "receipts" / "pilot-scorecard.json") or {}
    final = read_json(root / "receipts" / "final-delivery.json") or {}
    clips = sorted((root / "clips").glob("*.mp4")) if (root / "clips").is_dir() else []
    queue_contracts = _queue_contract_evidence(root)
    evidence = {
        "story": {
            "graph_present": _present(root, "drama-graph.json"),
            "semantic_ok": bool((control.get("semantic") or {}).get("ok")),
            "projection_current": not bool((control.get("projection") or {}).get("stale")),
        },
        "pilot": {
            "approval_present": bool(pilot),
            "scorecard_present": bool(scorecard),
            "user_approved": pilot_is_user_approved(pilot) if pilot else False,
        },
        "audio": {
            "tts_rehearsal": _present(root, "receipts/tts-rehearsal.json"),
            "mix_report": _present(root, "audio/mix_report.json"),
        },
        "motion": {"clip_count": len(clips), "clips_present": bool(clips)},
        "queue": queue_contracts,
        "delivery": {
            "final_delivery": bool(final),
            "final_mp4": _present(root, "final.mp4"),
            "subtitles": _present(root, "out/final.srt") or _present(root, "final.srt"),
        },
    }
    ready_for_bulk = bool(
        evidence["pilot"]["user_approved"]
        and evidence["story"]["semantic_ok"]
        and evidence["story"]["projection_current"]
        and queue_contracts["contracts_current"]
    )
    return {
        "ok": True,
        "kind": "production-evidence",
        "root": str(root),
        "evidence": evidence,
        "ready_for_bulk": ready_for_bulk,
        "next": []
        if ready_for_bulk
        else ["complete canonical story/graph review", "obtain pilot approval"],
    }
