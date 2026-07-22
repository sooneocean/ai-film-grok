"""Read-only story planning CLI routes."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from narrative_control import control_status, validate_narrative_graph
from story_plan import plan_status
from util import read_json


def validate(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    status = control_status(root)
    strict = bool(getattr(args, "strict", False))
    graph_path = root / "drama-graph.json"
    if strict and graph_path.is_file():
        report = validate_narrative_graph(read_json(graph_path), strict=True)
    else:
        report = dict(
            status.get("semantic") or {"ok": False, "issues": [{"code": "GRAPH_MISSING"}]}
        )
    report["strict_requested"] = strict
    report.update({"action": "validate", "root": str(root), "control": status})
    return report, 0 if report.get("ok") else 1


def status(root: Path) -> tuple[dict[str, Any], int]:
    report = plan_status(root)
    return report, 0
