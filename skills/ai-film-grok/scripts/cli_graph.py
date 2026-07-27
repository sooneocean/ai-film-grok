"""Read-only Drama Graph CLI routes."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from drama_graph import build_jobs_summary, graph_status, validate_graph
from narrative_control import control_status, projection_status


def add_graph_parsers(subparsers: Any) -> None:
    """Register graph commands without coupling parser setup to the CLI facade."""
    graph_parser = subparsers.add_parser(
        "graph",
        help="Vertical Drama Graph: derive|validate|status (from film-spec; Phase 1)",
    )
    graph_sub = graph_parser.add_subparsers(dest="graph_action", required=True)
    derive = graph_sub.add_parser(
        "derive", help="Derive drama-graph.json from film-spec (read-only projection)"
    )
    derive.add_argument("--root", required=True, help="Film root")
    derive.add_argument("--no-write", action="store_true", help="Do not write drama-graph.json")
    import_legacy = graph_sub.add_parser(
        "import", help="Explicitly import legacy film-spec into canonical drama-graph v2"
    )
    import_legacy.add_argument("--root", required=True, help="Film root")
    project = graph_sub.add_parser(
        "project", help="Project locked canonical drama-graph into film-spec"
    )
    project.add_argument("--root", required=True, help="Film root")
    project.add_argument("--force", action="store_true", help="Overwrite existing film-spec shots")
    validate_parser = graph_sub.add_parser("validate", help="Validate drama-graph.json structure")
    validate_parser.add_argument("--root", required=True, help="Film root")
    validate_parser.add_argument(
        "--derive-if-missing", action="store_true", help="Derive graph first if missing"
    )
    status_parser = graph_sub.add_parser("status", help="Graph counts + validate summary")
    status_parser.add_argument("--root", required=True, help="Film root")
    status_parser.add_argument(
        "--no-derive", action="store_true", help="Do not auto-derive if graph missing"
    )
    status_parser.add_argument(
        "--with-jobs", action="store_true", help="Include execution jobs_summary"
    )


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
