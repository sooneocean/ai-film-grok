"""Canonical Drama Graph → film-spec projection route."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from drama_graph import GRAPH_NAME, validate_graph
from narrative_control import graph_locked_for_projection
from story_plan import project_graph_to_film_spec
from util import read_json, write_json


def run(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    graph_path = root / GRAPH_NAME
    graph = read_json(graph_path)
    if not graph:
        return {
            "ok": False,
            "action": "project",
            "error": f"missing {graph_path} — run: aifilm plan run --root …",
        }, 1
    existing = read_json(root / "film-spec.json") or {}
    has_shots = any(
        isinstance(scene, dict) and scene.get("shots") for scene in (existing.get("scenes") or [])
    )
    if has_shots and not bool(getattr(args, "force", False)):
        return {
            "ok": False,
            "action": "project",
            "error": "film-spec already has shots; pass --force to overwrite",
        }, 1
    ready = graph_locked_for_projection(graph)
    if not ready.get("ok"):
        return {
            "ok": False,
            "action": "project",
            "error": "graph is not ready for projection",
            "missing_scopes": ready.get("missing_scopes"),
            "semantic": ready.get("semantic"),
        }, 1
    spec = project_graph_to_film_spec(
        graph,
        base_spec=existing,
        normalized=read_json(root / "receipts" / "story-normalize.json"),
    )
    output = root / "film-spec.json"
    write_json(output, spec)
    validation = validate_graph(graph)
    return {
        "ok": True,
        "action": "project",
        "path": str(output),
        "graph_ok": bool(validation.get("ok")),
        "shot_count": validation.get("shot_count"),
        "next": f'aifilm write-spec --root "{root}"',
    }, 0
