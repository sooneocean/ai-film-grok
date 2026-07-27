"""Read-only story planning CLI routes."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from narrative_control import control_status, validate_narrative_graph
from story_plan import plan_status
from util import read_json


def add_plan_parsers(subparsers: Any) -> None:
    """Register planning commands without coupling parser setup to the CLI facade."""
    plan_parser = subparsers.add_parser(
        "plan",
        help="Story plan: receive|normalize|run|validate|edit|lock|unlock|replan|project|status",
    )
    plan_sub = plan_parser.add_subparsers(dest="plan_action", required=True)
    receive = plan_sub.add_parser(
        "receive", help="Validate agent T2T StoryReception and write its receipt"
    )
    receive.add_argument("--root", required=True, help="Film root")
    receive.add_argument("--file", required=True, help="Agent-authored StoryReception JSON")
    receive.add_argument(
        "--force", action="store_true", help="Replace an existing reception before story lock"
    )
    normalize = plan_sub.add_parser(
        "normalize", help="story.normalize → receipts/story-normalize.json"
    )
    normalize.add_argument("--root", default=None, help="Optional film root to write receipt")
    normalize.add_argument("--text", default=None, help="Raw story / brief text")
    normalize.add_argument("--file", default=None, help="Path to .txt/.md story")
    normalize.add_argument("--title", default=None, help="Title override")
    run = plan_sub.add_parser(
        "run", help="Create draft plan: normalize→episode→scene→beat→shot→canonical drama-graph"
    )
    run.add_argument("--root", required=True, help="Film root")
    run.add_argument("--text", default=None, help="Raw story / one-liner idea")
    run.add_argument("--file", default=None, help="Path to story file")
    run.add_argument(
        "--received-file",
        default=None,
        help="Validated StoryReception JSON; uses its planning_text while preserving original source",
    )
    run.add_argument("--title", default=None, help="Title override")
    run.add_argument(
        "--target-duration", type=float, default=45.0, help="Target episode duration seconds"
    )
    run.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing film-spec shots / locked bible seed",
    )
    run.add_argument(
        "--apply-film-spec", action="store_true", help="Also write a draft film-spec projection"
    )
    run.add_argument("--no-film-spec", action="store_true", help="Do not write film-spec")
    run.add_argument(
        "--no-bible", action="store_true", help="Do not seed style-bible characters/locations"
    )
    project = plan_sub.add_parser("project", help="Project drama-graph → film-spec")
    project.add_argument("--root", required=True)
    project.add_argument("--force", action="store_true", help="Overwrite existing shots")
    validate_parser = plan_sub.add_parser(
        "validate", help="Validate story/beat/shot semantics and projection state"
    )
    validate_parser.add_argument("--root", required=True)
    validate_parser.add_argument("--strict", action="store_true")
    edit = plan_sub.add_parser("edit", help="Edit one unlocked narrative node")
    edit.add_argument("--root", required=True)
    edit.add_argument("--node", required=True, help="Node id/ref, e.g. story or ep01_sc01_bt03")
    edit.add_argument("--set", action="append", required=True, help="field=value; repeatable")
    lock = plan_sub.add_parser("lock", help="Lock one narrative scope after semantic validation")
    lock.add_argument("--root", required=True)
    lock.add_argument("--scope", choices=("story", "beats", "shots", "panels"), required=True)
    lock.add_argument("--user-phrase", required=True)
    unlock = plan_sub.add_parser("unlock", help="Unlock one narrative scope with an audit reason")
    unlock.add_argument("--root", required=True)
    unlock.add_argument("--scope", choices=("story", "beats", "shots", "panels"), required=True)
    unlock.add_argument("--reason", required=True)
    replan = plan_sub.add_parser(
        "replan", help="Mark a node and descendants stale without deleting media"
    )
    replan.add_argument("--root", required=True)
    replan.add_argument("--node", required=True)
    replan.add_argument(
        "--descendants", action="store_true", help="Required explicit confirmation flag"
    )
    status_parser = plan_sub.add_parser("status", help="Plan + graph status for film root")
    status_parser.add_argument("--root", required=True)


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
