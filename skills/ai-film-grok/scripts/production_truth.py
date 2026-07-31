"""Read-only audit that reconciles the project's authoritative records.

This is deliberately a reporting boundary.  It does not migrate manifests,
rebuild projections, or refresh receipts: a truth audit must never repair the
evidence it is meant to judge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manifest_truth import preflight_manifest
from production_book import ProductionBookError, read_production_book
from project_state import build_project_state
from util import read_json

AUTHORITY = {
    "creative_contract": "film-spec.json",
    "canonical_narrative": "drama-graph.json when canonical; otherwise film-spec.json",
    "asset_and_delivery_receipts": "manifest.json",
    "department_lifecycle": "production-book.json when present",
    "project_progress": "Professional 11-stage projection from project-state",
}


def audit_production_truth(root: Path | str) -> dict[str, Any]:
    """Return one fail-closed, non-mutating authority report for a film root."""
    base = Path(root).expanduser().resolve()
    blockers: list[str] = []

    spec_path = base / "film-spec.json"
    spec_present = spec_path.is_file()
    if not spec_present:
        blockers.append("FILM_SPEC_MISSING")

    manifest_path = base / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else None
    if not isinstance(manifest, dict):
        manifest_check: dict[str, Any] = {
            "present": False,
            "ok": False,
            "errors": ["manifest.json missing"],
        }
        blockers.append("MANIFEST_TRUTH_INVALID")
        gates: dict[str, Any] = {}
    else:
        manifest_check = {"present": True, **preflight_manifest(base, manifest)}
        if not manifest_check["ok"]:
            blockers.append("MANIFEST_TRUTH_INVALID")
        raw_gates = manifest.get("gates")
        gates = raw_gates if isinstance(raw_gates, dict) else {}

    graph_path = base / "drama-graph.json"
    if graph_path.is_file():
        from narrative_control import control_status

        graph_check = {"present": True, **control_status(base)}
        projection = graph_check.get("projection")
        if graph_check.get("canonical"):
            if not graph_check.get("ok"):
                blockers.append("CANONICAL_GRAPH_NOT_READY")
            if isinstance(projection, dict) and projection.get("stale"):
                blockers.append("CANONICAL_PROJECTION_STALE")
    else:
        graph_check = {"present": False, "canonical": False, "ok": True}

    book_path = base / "production-book.json"
    if book_path.is_file():
        try:
            book = read_production_book(base)
            book_check = {
                "present": True,
                "ok": True,
                "revision": book.get("revision"),
                "state": book.get("state"),
            }
        except (OSError, ProductionBookError, ValueError) as exc:
            book_check = {"present": True, "ok": False, "error": str(exc)}
            blockers.append("PRODUCTION_BOOK_INVALID")
    else:
        book_check = {"present": False, "ok": True}

    state = build_project_state(base, gates=gates, next_actions=[])
    if state.get("truth_conflicts"):
        blockers.append("PROJECT_STATE_CONFLICT")
    from production_evidence import build_evidence

    chain = build_evidence(base)
    queue = (chain.get("evidence") or {}).get("queue") or {}
    if not queue.get("contracts_current", True):
        blockers.append("QUEUE_CONTRACT_STALE")
    if graph_check.get("canonical") and queue.get("job_count") and not queue.get("chain_bound"):
        blockers.append("CANONICAL_QUEUE_CONTRACT_MISSING")

    return {
        "schema_version": 1,
        "kind": "production-truth-audit",
        "root": str(base),
        "ok": not blockers,
        "authority": AUTHORITY,
        "checks": {
            "film_spec": {"present": spec_present, "ok": spec_present},
            "manifest": manifest_check,
            "canonical_graph": graph_check,
            "production_book": book_check,
            "project_state": {
                "canonical_stage": state.get("canonical_stage"),
                "truth_conflicts": state.get("truth_conflicts") or [],
            },
            "production_chain": queue,
        },
        "blockers": blockers,
    }
