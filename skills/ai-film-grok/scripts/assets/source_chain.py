#!/usr/bin/env python3
"""Strict, hash-bound source lineage for shot media."""

from __future__ import annotations

import re
from typing import Any

from util import canonical_json_sha256

SOURCE_LEVELS = ("Style", "Cast", "StatePhoto", "Keyframe", "Clip", "PromotedTail")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class SourceChainError(ValueError):
    """The requested source transition would break provenance."""


def _stable_hash(value: Any) -> str:
    return canonical_json_sha256(value)


def _node_hash(node: dict[str, Any], shot_id: str) -> str:
    return _stable_hash(
        {
            "shotId": shot_id,
            "level": node.get("level"),
            "assetRef": node.get("assetRef"),
            "assetHash": node.get("assetHash"),
            "parentRef": node.get("parentRef"),
            "parentHash": node.get("parentHash"),
            "wardrobeState": node.get("wardrobeState"),
        }
    )


def new_source_chain(shot_id: str) -> dict[str, Any]:
    shot = str(shot_id).strip()
    if not shot:
        raise SourceChainError("shot_id is required")
    chain = {
        "schema_version": 1,
        "kind": "shot-source-chain",
        "shotId": shot,
        "levels": list(SOURCE_LEVELS),
        "nodes": [],
    }
    chain["chainHash"] = _chain_hash(chain)
    return chain


def _chain_hash(chain: dict[str, Any]) -> str:
    return _stable_hash(
        {
            "kind": chain.get("kind"),
            "shotId": chain.get("shotId"),
            "levels": chain.get("levels"),
            "nodes": chain.get("nodes"),
        }
    )


def validate_source_chain(
    chain: dict[str, Any], *, require_complete: bool = False
) -> dict[str, Any]:
    errors: list[str] = []
    shot_id = str(chain.get("shotId") or "").strip() if isinstance(chain, dict) else ""
    if not shot_id:
        errors.append("shotId is required")
    if chain.get("kind") != "shot-source-chain":
        errors.append("kind must be shot-source-chain")
    if chain.get("levels") != list(SOURCE_LEVELS):
        errors.append("levels do not match the canonical source chain")
    nodes = chain.get("nodes") if isinstance(chain, dict) else None
    if not isinstance(nodes, list):
        return {"ok": False, "complete": False, "errors": ["nodes must be an array"]}
    if len(nodes) > len(SOURCE_LEVELS):
        errors.append("source chain has more nodes than levels")

    locked_wardrobe: str | None = None
    previous: dict[str, Any] | None = None
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{index}] must be an object")
            continue
        expected_level = SOURCE_LEVELS[index] if index < len(SOURCE_LEVELS) else None
        if node.get("level") != expected_level:
            errors.append(f"nodes[{index}] expected {expected_level}, got {node.get('level')}")
        if not _SHA256.fullmatch(str(node.get("assetHash") or "")):
            errors.append(f"{node.get('level')}: assetHash must be SHA-256")
        if node.get("hash") != _node_hash(node, shot_id):
            errors.append(f"{node.get('level')}: stale node hash")
        if previous is None:
            if node.get("parentRef") is not None or node.get("parentHash") is not None:
                errors.append("Style must not have a parent")
        else:
            if node.get("parentRef") != previous.get("assetRef"):
                errors.append(f"{node.get('level')}: parentRef is not the immediate source")
            if node.get("parentHash") != previous.get("hash"):
                errors.append(f"{node.get('level')}: stale parent hash")

        wardrobe = str(node.get("wardrobeState") or "").strip() or None
        if node.get("level") == "StatePhoto":
            if not wardrobe:
                errors.append("StatePhoto: wardrobeState is required")
            locked_wardrobe = wardrobe
        elif locked_wardrobe is not None and wardrobe != locked_wardrobe:
            errors.append(
                f"{node.get('level')}: wardrobe regression {wardrobe!r} != {locked_wardrobe!r}"
            )
        previous = node

    complete = len(nodes) == len(SOURCE_LEVELS)
    if require_complete and not complete:
        errors.append(f"incomplete source chain: {len(nodes)}/{len(SOURCE_LEVELS)}")
    if chain.get("chainHash") != _chain_hash(chain):
        errors.append("stale chain hash")
    return {
        "ok": not errors,
        "complete": complete,
        "nextLevel": SOURCE_LEVELS[len(nodes)] if len(nodes) < len(SOURCE_LEVELS) else None,
        "errors": errors,
    }


def append_source(
    chain: dict[str, Any],
    level: str,
    asset_ref: str,
    asset_hash: str,
    *,
    parent_ref: str | None = None,
    wardrobe_state: str | None = None,
) -> dict[str, Any]:
    """Append exactly the next lineage level after validating the current chain."""
    report = validate_source_chain(chain)
    if not report["ok"]:
        raise SourceChainError("; ".join(report["errors"]))
    expected = report["nextLevel"]
    if expected is None:
        raise SourceChainError("source chain is already complete")
    if level != expected:
        raise SourceChainError(f"expected {expected}, got {level}")
    asset_ref = str(asset_ref).strip()
    if not asset_ref:
        raise SourceChainError("asset_ref is required")
    if not _SHA256.fullmatch(str(asset_hash)):
        raise SourceChainError("asset_hash must be a lowercase SHA-256")

    nodes = chain["nodes"]
    previous = nodes[-1] if nodes else None
    expected_parent = previous.get("assetRef") if previous else None
    if parent_ref != expected_parent:
        raise SourceChainError(f"{level}: parent_ref must be immediate source {expected_parent!r}")
    locked_wardrobe = next(
        (
            str(node.get("wardrobeState"))
            for node in nodes
            if node.get("level") == "StatePhoto" and node.get("wardrobeState")
        ),
        None,
    )
    wardrobe = str(wardrobe_state or "").strip() or None
    if level == "StatePhoto" and not wardrobe:
        raise SourceChainError("StatePhoto requires wardrobe_state")
    if locked_wardrobe is not None and wardrobe != locked_wardrobe:
        raise SourceChainError(f"wardrobe regression: {wardrobe!r} != {locked_wardrobe!r}")

    node = {
        "level": level,
        "assetRef": asset_ref,
        "assetHash": asset_hash,
        "parentRef": expected_parent,
        "parentHash": previous.get("hash") if previous else None,
        "wardrobeState": wardrobe,
    }
    node["hash"] = _node_hash(node, str(chain["shotId"]))
    nodes.append(node)
    chain["chainHash"] = _chain_hash(chain)
    return node
