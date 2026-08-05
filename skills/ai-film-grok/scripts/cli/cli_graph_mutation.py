"""Graph mutation command domain extracted from :mod:`aifilm_grok`.

The command contract stays intentionally small: handlers return a JSON-safe
report and an exit code; the top-level CLI owns output formatting and errors.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from drama_graph import derive_graph, graph_path, validate_graph
from narrative_control import (
    GRAPH_SCHEMA_VERSION,
    draft_director_board,
    ensure_graph_controls,
    graph_content_sha256,
    graph_locked_for_projection,
)
from story_plan import project_graph_to_film_spec
from util import utc_now, write_json


class GraphMutationError(RuntimeError):
    """User-facing graph mutation error."""


def run(args: argparse.Namespace, root: Path) -> tuple[dict[str, Any], int]:
    """Execute derive/import/project without printing or parsing CLI state."""
    action = str(getattr(args, "graph_action", "") or "")
    root = Path(root).expanduser().resolve()
    if action == "derive":
        path = graph_path(root)
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise GraphMutationError(
                "canonical drama-graph exists; use aifilm graph project or plan edit, not graph derive"
            )
        graph = derive_graph(root, write=not bool(getattr(args, "no_write", False)))
        validation = validate_graph(graph)
        report = {
            "ok": bool(validation.get("ok")),
            "action": "derive",
            "path": str(path),
            "shot_count": validation.get("shot_count"),
            "warnings": (graph.get("warnings") or []) + (validation.get("warnings") or []),
            "errors": validation.get("errors") or [],
            "project": graph.get("project"),
            "episode_count": len(graph.get("episodes") or []),
        }
        return report, 0 if report["ok"] else 1

    if action == "import":
        path = graph_path(root)
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise GraphMutationError(
                "canonical drama-graph already exists; refusing legacy import overwrite"
            )
        graph = derive_graph(root, write=False)
        spec_path = root / "film-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.is_file() else {}
        director_intent = (
            spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
        )
        graph["schema_version"] = GRAPH_SCHEMA_VERSION
        graph["derived_from"] = {
            **(graph.get("derived_from") or {}),
            "mode": "legacy-import",
            "imported_at": utc_now(),
        }
        graph["story"] = {
            "genre": str(spec.get("genre") or "adult"),
            "premise": str(spec.get("description") or director_intent.get("logline") or ""),
            "logline": str(director_intent.get("logline") or spec.get("description") or ""),
            "theme": str(director_intent.get("theme") or ""),
            "protagonist_ids": list(director_intent.get("cast") or spec.get("cast_ids") or []),
            "protagonist_goal": str(director_intent.get("protagonist_goal") or ""),
            "protagonist_want": str(director_intent.get("protagonist_want") or ""),
            "protagonist_need": str(director_intent.get("protagonist_need") or ""),
            "protagonist_arc": str(director_intent.get("protagonist_arc") or ""),
            "opposition": str(director_intent.get("opposition") or ""),
            "stakes": str(director_intent.get("stakes") or ""),
            "climax_choice": str(director_intent.get("climax_choice") or ""),
            "ending_hook": str(director_intent.get("ending_hook") or ""),
            "emotional_arc": list(director_intent.get("emotional_arc") or []),
            "act_structure": director_intent.get("act_structure")
            if isinstance(director_intent.get("act_structure"), dict)
            else {},
            "pace_chart": list(director_intent.get("pace_chart") or []),
            "constraints": list(director_intent.get("taboos") or []),
            "status": "needs_authoring",
        }
        for episode in graph.get("episodes") or []:
            for scene in episode.get("scenes") or []:
                for beat in scene.get("beats") or []:
                    if not isinstance(beat, dict):
                        continue
                    for field in (
                        "objective",
                        "obstacle",
                        "tactic",
                        "turn",
                        "outcome",
                        "state_delta",
                    ):
                        beat.setdefault(field, "needs_authoring")
                    beat.setdefault("director_board", draft_director_board())
        ensure_graph_controls(graph)
        write_json(path, graph)
        receipt = root / "receipts" / "graph-migration.json"
        write_json(
            receipt,
            {
                "schema_version": 1,
                "kind": "drama-graph-migration",
                "at": utc_now(),
                "source": "film-spec.json",
                "target": "drama-graph.json",
                "target_schema_version": GRAPH_SCHEMA_VERSION,
                "content_sha256": graph_content_sha256(graph),
                "note": "legacy import is draft-only; complete director_board and lock scopes before projection",
            },
        )
        return {
            "ok": True,
            "action": "import",
            "path": str(path),
            "receipt": str(receipt),
            "state": graph.get("state"),
            "content_sha256": graph_content_sha256(graph),
        }, 0

    if action == "project":
        path = graph_path(root)
        graph = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if int(graph.get("schema_version") or 0) < GRAPH_SCHEMA_VERSION:
            raise GraphMutationError(
                "graph project requires canonical graph v2; run aifilm graph import first"
            )
        ready = graph_locked_for_projection(graph)
        if not ready.get("ok"):
            raise GraphMutationError(
                "graph is not ready for projection: "
                + ", ".join(
                    ready.get("missing_scopes")
                    or [
                        item.get("code", "NARRATIVE")
                        for item in (ready.get("semantic") or {}).get("errors", [])
                    ]
                )
            )
        spec_path = root / "film-spec.json"
        existing = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.is_file() else {}
        has_shots = any(
            isinstance(scene, dict) and scene.get("shots")
            for scene in (existing.get("scenes") or [])
        )
        if has_shots and not bool(getattr(args, "force", False)):
            raise GraphMutationError(
                "film-spec already has shots; pass --force to overwrite projection"
            )
        norm_path = root / "receipts" / "story-normalize.json"
        normalized = (
            json.loads(norm_path.read_text(encoding="utf-8")) if norm_path.is_file() else None
        )
        spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=normalized)
        write_json(spec_path, spec)
        return {
            "ok": True,
            "action": "project",
            "path": str(spec_path),
            "source_revision": graph.get("revision"),
            "source_sha256": graph_content_sha256(graph),
        }, 0

    raise GraphMutationError(f"unknown graph action {action!r}")
