"""Read-only Drama Graph CLI routes."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from drama_graph import build_jobs_summary, graph_status, validate_graph
from narrative_control import control_status, projection_status


def validate(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    if (
        bool(getattr(args, "derive_if_missing", False))
        and not (root / "drama-graph.json").is_file()
    ):
        from drama_graph import derive_graph

        derive_graph(root, write=True)
    report = validate_graph(root=root)
    report["narrative"] = control_status(root)
    report["action"] = "validate"
    report["path"] = str(root / "drama-graph.json")
    return report, 0 if report.get("ok") else 1


def status(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    auto = bool(getattr(args, "derive_if_missing", True)) and not bool(
        getattr(args, "no_derive", False)
    )
    report = graph_status(root, auto_derive=auto)
    if bool(getattr(args, "with_jobs", False)):
        report["jobs_summary"] = build_jobs_summary(root)
    report["control"] = control_status(root)
    report["projection"] = projection_status(root)
    return report, 0 if report.get("ok") else 1
