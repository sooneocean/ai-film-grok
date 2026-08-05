"""Hash-bound contracts linking plan, assets, queue work, and later evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import canonical_json_sha256, read_json, sha256_file


class ProductionChainError(ValueError):
    """A queue job no longer represents the current production truth."""


def _hash_if_file(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def _asset_refs(registry: dict[str, Any], shot_id: str) -> list[dict[str, Any]]:
    rows = registry.get("characterStatesTimeline")
    if not isinstance(rows, list):
        return []
    return [
        dict(row)
        for row in rows
        if isinstance(row, dict) and str(row.get("shotId") or "") == shot_id
    ]


def build_shot_contract(root: Path | str, shot_id: str) -> dict[str, Any]:
    """Snapshot the current plan and asset inputs for one queue job.

    Legacy roots remain explicitly unbound so an old project is never given a
    false claim of canonical provenance. Canonical graph projects must have a
    current executable projection and an asset registry before queue admission.
    """
    base = Path(root).expanduser().resolve()
    spec_path = base / "film-spec.json"
    graph_path = base / "drama-graph.json"
    assets_path = base / "assets-registry.json"
    spec_sha = _hash_if_file(spec_path)
    graph_sha = _hash_if_file(graph_path)
    registry_sha = _hash_if_file(assets_path)
    registry = read_json(assets_path) if assets_path.is_file() else {}
    registry = registry if isinstance(registry, dict) else {}
    errors: list[str] = []

    from narrative_control import control_status

    control = control_status(base)
    canonical = bool(control.get("canonical"))
    if canonical:
        if not control.get("ok"):
            errors.append("CANONICAL_GRAPH_NOT_READY")
        if not graph_sha:
            errors.append("DRAMA_GRAPH_MISSING")
        if not spec_sha:
            errors.append("FILM_SPEC_MISSING")
        if not registry_sha:
            errors.append("ASSET_REGISTRY_MISSING")
        else:
            from asset_registry import assets_check

            assets = assets_check(base, sync_first=False)
            if not assets.get("ok"):
                errors.append("ASSET_REGISTRY_NOT_READY")
    mode = "canonical" if canonical else "bound" if spec_sha else "legacy-unbound"
    contract: dict[str, Any] = {
        "schema_version": 1,
        "kind": "shot-production-contract",
        "ok": not errors,
        "mode": mode,
        "shot_id": str(shot_id),
        "plan": {
            "film_spec_sha256": spec_sha,
            "drama_graph_sha256": graph_sha,
            "canonical": canonical,
            "projection_current": not bool((control.get("projection") or {}).get("stale")),
        },
        "assets": {
            "registry_sha256": registry_sha,
            "state_refs": _asset_refs(registry, str(shot_id)),
        },
        "errors": errors,
    }
    contract["contract_sha256"] = canonical_json_sha256(contract)
    return contract


def canonical_contract_required(root: Path | str) -> bool:
    """Whether this project must reject an unbound queue job as corrupt."""
    from narrative_control import control_status

    return bool(control_status(Path(root).expanduser().resolve()).get("canonical"))


def queue_contract_is_current(root: Path | str, contract: object) -> dict[str, Any]:
    """Compare a stored queue contract with the current authoritative inputs."""
    if not isinstance(contract, dict) or contract.get("kind") != "shot-production-contract":
        return {"ok": False, "errors": ["QUEUE_CONTRACT_MISSING"]}
    if contract.get("mode") == "legacy-unbound":
        return {"ok": True, "errors": [], "mode": "legacy-unbound"}
    current = build_shot_contract(root, str(contract.get("shot_id") or ""))
    errors = list(current.get("errors") or [])
    old_plan = contract.get("plan") if isinstance(contract.get("plan"), dict) else {}
    new_plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
    old_assets = contract.get("assets") if isinstance(contract.get("assets"), dict) else {}
    new_assets = current.get("assets") if isinstance(current.get("assets"), dict) else {}
    if old_plan.get("film_spec_sha256") != new_plan.get("film_spec_sha256"):
        errors.append("FILM_SPEC_CHANGED")
    if old_plan.get("drama_graph_sha256") != new_plan.get("drama_graph_sha256"):
        errors.append("DRAMA_GRAPH_CHANGED")
    if old_assets.get("registry_sha256") != new_assets.get("registry_sha256"):
        errors.append("ASSET_REGISTRY_CHANGED")
    if old_assets.get("state_refs") != new_assets.get("state_refs"):
        errors.append("SHOT_ASSET_STATE_CHANGED")
    return {"ok": not errors, "errors": sorted(set(errors)), "current": current}


def require_current_queue_contract(root: Path | str, contract: object) -> None:
    report = queue_contract_is_current(root, contract)
    if not report["ok"]:
        raise ProductionChainError(
            "queue job source contract is stale: " + ", ".join(report["errors"])
        )
