#!/usr/bin/env python3
"""Read-only per-shot projection of exact department node references."""

from __future__ import annotations

from typing import Any

from shot_inventory import flatten_shot_inventory
from util import canonical_json_sha256

_VISUAL_GROUPS = {
    "visual": ("face", "hair", "makeup", "wardrobe"),
    "productionDesign": ("location", "art", "prop", "cinematography"),
}


class ShotPackageError(ValueError):
    """A shot or required hash-bound node could not be projected."""


def _stable_hash(value: Any) -> str:
    return canonical_json_sha256(value)


def _find_shot(graph: dict[str, Any], shot_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    for episode in graph.get("episodes") or []:
        if not isinstance(episode, dict):
            continue
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for beat in scene.get("beats") or []:
                if not isinstance(beat, dict):
                    continue
                for shot in beat.get("shots") or []:
                    if isinstance(shot, dict) and str(shot.get("id")) == shot_id:
                        return shot, {
                            "episodeId": str(episode.get("id") or ""),
                            "sceneId": str(scene.get("id") or ""),
                            "beatId": str(beat.get("id") or ""),
                        }
    raise ShotPackageError(
        f"unknown shot_id={shot_id!r}; inventory={flatten_shot_inventory(graph)}"
    )


def _ref(node: dict[str, Any], expected_id: str) -> dict[str, Any]:
    node_id = str(node.get("id") or expected_id)
    if node.get("state") != "locked" or not isinstance(node.get("approval_ref"), str):
        raise ShotPackageError(f"required node is not currently locked: {node_id}")
    digest = _stable_hash(
        {
            "id": node_id,
            "revision": node.get("revision"),
            "source_refs": node.get("source_refs"),
            "dependency_refs": node.get("dependency_refs"),
            "state": node.get("state"),
            "approval_ref": node.get("approval_ref"),
            "stale_reasons": node.get("stale_reasons"),
            "data": node.get("data"),
        }
    )
    return {
        "nodeId": node_id,
        "revision": node.get("revision"),
        "state": node.get("state"),
        "approvalRef": node.get("approval_ref"),
        "hash": digest,
    }


def _refs(bible: dict[str, Any], department: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    nodes = bible.get("nodes") if isinstance(bible, dict) else None
    if not isinstance(nodes, dict):
        raise ShotPackageError(f"{department} bible nodes are required")
    result: list[dict[str, str]] = []
    for key in keys:
        node = nodes.get(key)
        if not isinstance(node, dict):
            raise ShotPackageError(f"missing {department}.{key}.primary")
        result.append(_ref(node, f"{department}.{key}.primary"))
    return result


def _derived_ref(node_id: str, data: Any) -> dict[str, str]:
    return {"nodeId": node_id, "hash": _stable_hash({"nodeId": node_id, "data": data})}


def _validate_shot_contract(shot: dict[str, Any], shot_id: str) -> None:
    missing: list[str] = []
    if not str(shot.get("narrativePurpose") or shot.get("dramaticFunction") or "").strip():
        missing.append("narrativePurpose|dramaticFunction")
    if not str(shot.get("locationId") or "").strip():
        missing.append("locationId")
    try:
        if float(shot.get("duration_sec") or 0) <= 0:
            missing.append("duration_sec")
    except (TypeError, ValueError):
        missing.append("duration_sec")
    if not isinstance(shot.get("dsl"), dict) or not shot["dsl"]:
        missing.append("dsl")
    characters = shot.get("characterIds")
    environment_only = shot.get("environmentOnly") is True
    if not environment_only and (not isinstance(characters, list) or not characters):
        missing.append("characterIds|environmentOnly")
    if not environment_only and (
        not isinstance(shot.get("performance"), dict) or not shot["performance"]
    ):
        missing.append("performance")
    if missing:
        raise ShotPackageError(f"shot {shot_id} is missing execution fields: {', '.join(missing)}")


def compile_shot_package(
    shot_id: str,
    *,
    graph: dict[str, Any],
    visual_bible: dict[str, Any],
    audio_bible: dict[str, Any],
    post_bible: dict[str, Any],
) -> dict[str, Any]:
    """Project one shot without copying mutable bible payloads."""
    shot_id = str(shot_id).strip()
    shot, ancestry = _find_shot(graph, shot_id)
    _validate_shot_contract(shot, shot_id)
    narrative_data = {**ancestry, "shotId": shot_id, "shot": shot}
    performance_data = {
        "characterIds": shot.get("characterIds") or [],
        "performance": shot.get("performance") or {},
    }
    dialogue_data = {
        "dialogueLineIds": shot.get("dialogueLineIds") or [],
        "dialogue": shot.get("dialogue"),
        "nar": shot.get("nar"),
    }
    departments = {
        "narrative": [_derived_ref(f"narrative.shot.{shot_id}", narrative_data)],
        "visual": _refs(visual_bible, "visual", _VISUAL_GROUPS["visual"]),
        "productionDesign": _refs(visual_bible, "visual", _VISUAL_GROUPS["productionDesign"]),
        "performance": [
            _derived_ref(f"performance.shot.{shot_id}", performance_data),
            _derived_ref(f"dialogue.shot.{shot_id}", dialogue_data),
        ],
        "audio": _refs(audio_bible, "audio", tuple((audio_bible.get("nodes") or {}).keys())),
        "post": _refs(post_bible, "post", tuple((post_bible.get("nodes") or {}).keys())),
    }
    package: dict[str, Any] = {
        "schema_version": 1,
        "kind": "shot-package",
        "readOnly": True,
        "shotId": shot_id,
        "departments": departments,
    }
    package["packageHash"] = _stable_hash(package)
    return package


def check_shot_package_current(
    package: dict[str, Any],
    *,
    graph: dict[str, Any],
    visual_bible: dict[str, Any],
    audio_bible: dict[str, Any],
    post_bible: dict[str, Any],
) -> dict[str, Any]:
    expected = compile_shot_package(
        str(package.get("shotId") or ""),
        graph=graph,
        visual_bible=visual_bible,
        audio_bible=audio_bible,
        post_bible=post_bible,
    )
    old_refs = {
        ref["nodeId"]: ref["hash"]
        for refs in (package.get("departments") or {}).values()
        for ref in refs
        if isinstance(ref, dict) and ref.get("nodeId")
    }
    new_refs = {
        ref["nodeId"]: ref["hash"] for refs in expected["departments"].values() for ref in refs
    }
    changed = sorted(
        node_id
        for node_id in old_refs.keys() | new_refs.keys()
        if old_refs.get(node_id) != new_refs.get(node_id)
    )
    current = package.get("packageHash") == expected["packageHash"] and package.get(
        "packageHash"
    ) == _stable_hash({key: value for key, value in package.items() if key != "packageHash"})
    return {
        "ok": current,
        "current": current,
        "shotId": package.get("shotId"),
        "packageHash": package.get("packageHash"),
        "expectedPackageHash": expected["packageHash"],
        "changedNodeIds": changed,
    }


def is_shot_package_current(package: dict[str, Any], **sources: Any) -> bool:
    return bool(check_shot_package_current(package, **sources)["current"])
