"""Pure canonical project-state projection shared by status and dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

PROJECT_STATE_RELATIVE = Path("receipts/project-state.json")


def _hash_if_present(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def _truth_conflicts(
    base: Path, gates: dict[str, Any], workflow: dict[str, Any]
) -> list[dict[str, str]]:
    """Expose incompatible projections before any downstream media mutation."""
    conflicts: list[dict[str, str]] = []
    stage = str(workflow.get("current_stage") or "")
    if gates.get("final_complete") is True and stage not in {"master_lock", ""}:
        conflicts.append(
            {
                "code": "FINAL_BEFORE_CANONICAL_MASTER",
                "message": f"final_complete conflicts with canonical stage {stage}",
            }
        )
    if gates.get("desktop_exported") is True and gates.get("final_complete") is not True:
        conflicts.append(
            {
                "code": "EXPORT_WITHOUT_FINAL",
                "message": "desktop export exists without final_complete",
            }
        )
    manifest = read_json(base / "manifest.json") or {}
    output = (
        (manifest.get("outputs") or {}).get("final_film") if isinstance(manifest, dict) else None
    )
    if gates.get("final_complete") is True and not isinstance(output, dict):
        conflicts.append(
            {
                "code": "FINAL_GATE_WITHOUT_OUTPUT",
                "message": "final_complete has no manifest final_film receipt",
            }
        )
    return conflicts


def build_project_state(
    root: Path | str,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
    next_actions: list[dict[str, Any]] | None = None,
    next_cmd: str | None = None,
    next_id: str | None = None,
) -> dict[str, Any]:
    """Build one immutable snapshot without writing receipts, manifests, or HUD."""
    base = Path(root).expanduser().resolve()
    from next_actions import build_next_actions, detect_pipeline_stage

    resolved_gates = dict(gates or {})
    pipeline = detect_pipeline_stage(
        base,
        gates=resolved_gates,
        open_reshoot_count=int(open_reshoot_count or 0),
    )
    actions = (
        list(next_actions)
        if next_actions is not None
        else build_next_actions(
            base,
            gates=resolved_gates,
            open_reshoot_count=int(open_reshoot_count or 0),
        )
    )
    resolved_next_cmd = next_cmd or (actions[0].get("cmd") if actions else None)
    resolved_next_id = next_id or (actions[0].get("id") if actions else None)
    workflow = pipeline.get("workflow") if isinstance(pipeline.get("workflow"), dict) else {}
    conflicts = _truth_conflicts(base, resolved_gates, workflow)
    spec = read_json(base / "film-spec.json") or {}
    longform = None
    if spec.get("production_mode") == "longform":
        from longform import longform_status

        longform = longform_status(base)
    semantic: dict[str, Any] = {
        "schema_version": 1,
        "kind": "project-state-snapshot",
        "root": str(base),
        "production_mode": str(spec.get("production_mode") or "shortform"),
        "canonical_stage": workflow.get("current_stage") or pipeline.get("stage"),
        "canonical_stage_index": workflow.get("stage_index") or pipeline.get("stage_index"),
        "canonical_stage_total": workflow.get("stage_total") or pipeline.get("stage_total"),
        "internal_stage": pipeline.get("stage"),
        "blockers": list(pipeline.get("blockers") or []) + [row["code"] for row in conflicts],
        "truth_conflicts": conflicts,
        "gates": resolved_gates,
        "open_reshoot_count": int(open_reshoot_count or 0),
        "next_id": resolved_next_id,
        "next_cmd": resolved_next_cmd,
        "next_action": actions[0] if actions else None,
        "next_actions": actions,
        "source_hashes": {
            "graph": _hash_if_present(base / "drama-graph.json"),
            "spec": _hash_if_present(base / "film-spec.json"),
            "timeline": _hash_if_present(base / "timeline.json"),
            "manifest": _hash_if_present(base / "manifest.json"),
        },
        "longform": longform,
    }
    semantic["state_sha256"] = canonical_json_sha256(semantic)
    return semantic


def persist_project_state(root: Path | str, snapshot: dict[str, Any]) -> Path:
    base = Path(root).expanduser().resolve()
    payload = {**snapshot, "persisted_at": utc_now()}
    path = base / PROJECT_STATE_RELATIVE
    write_json(path, payload)
    return path
