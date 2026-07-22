"""Read-only production evidence ledger for director and batch gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from narrative_control import control_status
from production_gates import pilot_is_user_approved
from util import read_json


def _present(root: Path, relative: str) -> bool:
    return (root / relative).is_file()


def build_evidence(root: Path) -> dict[str, Any]:
    control = control_status(root)
    pilot = read_json(root / "receipts" / "pilot-approval.json") or {}
    scorecard = read_json(root / "receipts" / "pilot-scorecard.json") or {}
    final = read_json(root / "receipts" / "final-delivery.json") or {}
    clips = sorted((root / "clips").glob("*.mp4")) if (root / "clips").is_dir() else []
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
