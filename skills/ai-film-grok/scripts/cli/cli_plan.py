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
        "--story-mode",
        choices=("narrative", "documentary", "monologue", "experimental"),
        default="narrative",
        help="Narrative defaults to dialogue screenplay; other modes are explicit exceptions",
    )
    run.add_argument(
        "--target-duration", type=float, default=45.0, help="Target episode duration seconds"
    )
    run.add_argument(
        "--production-mode",
        choices=("shortform", "longform"),
        default="shortform",
        help="shortform keeps the existing workflow; longform v1 requires 480–900 seconds",
    )
    run.add_argument(
        "--received",
        action="store_true",
        help="Use the canonical receipts/story-reception.json written by plan receive",
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
    validate_structure = plan_sub.add_parser(
        "validate-structure",
        help="Story structure gate: goal/opposition/scene turn/beat layer (Film Production OS W1)",
    )
    validate_structure.add_argument("--root", required=True)
    validate_structure.add_argument(
        "--strict",
        action="store_true",
        help="Fail closed on weak structure; blocks media_spend_allowed",
    )
    shot_cards = plan_sub.add_parser(
        "shot-cards",
        help="Export Shot Cards + SHOT_LIST.md from film-spec (Film Production OS W2)",
    )
    shot_cards.add_argument("--root", required=True)
    shot_cards.add_argument(
        "--strict-purpose",
        action="store_true",
        help="Warn on purposes outside SHOT_PURPOSES enum",
    )
    shot_cards.add_argument(
        "--no-write",
        action="store_true",
        help="Dry-run: do not write shot-cards/ files",
    )
    edit = plan_sub.add_parser("edit", help="Edit one unlocked narrative node")
    edit.add_argument("--root", required=True)
    edit.add_argument("--node", required=True, help="Node id/ref, e.g. story or ep01_sc01_bt03")
    edit.add_argument("--set", action="append", required=True, help="field=value; repeatable")
    lock = plan_sub.add_parser("lock", help="Lock one narrative scope after semantic validation")
    lock.add_argument("--root", required=True)
    lock.add_argument("--scope", choices=("story", "beats", "shots", "panels"), required=True)
    lock.add_argument("--user-phrase", required=True)
    lock.add_argument(
        "--strict",
        action="store_true",
        help="Story scope: require script-value-debrief present+confirmed (or AIFILM_DEBRIEF_STRICT=1)",
    )
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

    debrief = plan_sub.add_parser(
        "debrief",
        help="Script-value-debrief: status|seed|write|confirm|validate (L0–L4 pre-lock)",
    )
    debrief.add_argument("--root", required=True, help="Film root")
    debrief.add_argument(
        "--action",
        choices=("status", "seed", "write", "confirm", "validate"),
        default="status",
        help="status=check receipt; seed=from story-reception; write=from --file; "
        "confirm=human sign-off; validate=structure check",
    )
    debrief.add_argument(
        "--file",
        default=None,
        help="Agent-authored debrief JSON (write) or reception JSON (seed override)",
    )
    debrief.add_argument(
        "--user-phrase",
        default=None,
        help="Required for confirm — human-visible sign-off (agent must not invent)",
    )
    debrief.add_argument("--strict", action="store_true", help="Hard-fail missing/invalid")
    debrief.add_argument(
        "--force",
        action="store_true",
        help="write: overwrite; confirm: allow confirm despite structure warnings",
    )
    debrief.add_argument("--receipt", type=Path, default=None, help="Optional copy of report JSON")


def run_debrief(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    """CLI body for plan debrief."""
    from script_value_debrief import (
        check_root,
        confirm_debrief,
        load_debrief,
        receipt_path,
        seed_from_reception,
        user_facing_summary,
        validate_debrief,
        write_debrief,
    )
    from util import write_json

    action = str(getattr(args, "action", "status") or "status")
    strict = bool(getattr(args, "strict", False))
    report: dict[str, Any]

    if action == "status":
        report = check_root(root, strict=strict)
        deb = load_debrief(root)
        if deb:
            report["user_summary"] = user_facing_summary(deb)
            report["confirmed_by_user"] = deb.get("confirmed_by_user") is True
    elif action == "validate":
        deb = load_debrief(root)
        report = validate_debrief(deb, strict=strict, require_confirmed=strict)
        report["root"] = str(root)
        report["receipt"] = str(receipt_path(root))
        if deb:
            report["user_summary"] = user_facing_summary(deb)
    elif action == "seed":
        from story_reception import ReceptionError, load_story_reception

        recv_path = getattr(args, "file", None)
        path = (
            Path(str(recv_path)).expanduser().resolve()
            if recv_path
            else root / "receipts" / "story-reception.json"
        )
        try:
            reception = load_story_reception(path)
        except ReceptionError as exc:
            return {"ok": False, "action": "seed", "error": str(exc)}, 1
        draft = seed_from_reception(reception)
        out = write_debrief(root, draft)
        report = {
            "ok": True,
            "action": "seed",
            "path": str(out),
            "note": "draft only — fill beat_cards + must_keep then confirm",
            "user_summary": user_facing_summary(draft),
            "validation": validate_debrief(draft, strict=False),
        }
    elif action == "write":
        file_s = getattr(args, "file", None)
        if not file_s:
            return {"ok": False, "action": "write", "error": "--file required"}, 1
        src = Path(str(file_s)).expanduser().resolve()
        if not src.is_file():
            return {"ok": False, "action": "write", "error": f"file not found: {src}"}, 1
        existing = receipt_path(root)
        if existing.is_file() and not bool(getattr(args, "force", False)):
            return {
                "ok": False,
                "action": "write",
                "error": f"{existing} exists; pass --force to overwrite",
            }, 1
        payload = read_json(src) or {}
        if not isinstance(payload, dict):
            return {"ok": False, "action": "write", "error": "debrief file must be object"}, 1
        out = write_debrief(root, payload)
        loaded = load_debrief(root)
        report = {
            "ok": True,
            "action": "write",
            "path": str(out),
            "validation": validate_debrief(loaded, strict=strict),
            "user_summary": user_facing_summary(loaded or {}),
        }
        if strict and not report["validation"].get("ok"):
            report["ok"] = False
    elif action == "confirm":
        phrase = getattr(args, "user_phrase", None)
        try:
            report = confirm_debrief(
                root,
                user_phrase=str(phrase or ""),
                force=bool(getattr(args, "force", False)),
            )
            report["action"] = "confirm"
        except (FileNotFoundError, ValueError) as exc:
            return {"ok": False, "action": "confirm", "error": str(exc)}, 1
    else:
        return {"ok": False, "error": f"unknown debrief action {action!r}"}, 1

    report.setdefault("action", action)
    report.setdefault("root", str(root))
    if getattr(args, "receipt", None):
        write_json(Path(args.receipt).expanduser().resolve(), report)
        report["receipt_out"] = str(Path(args.receipt).expanduser().resolve())
    return report, 0 if report.get("ok") is not False else 1


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
    try:
        from script_value_debrief import attach_to_plan_validate

        report = attach_to_plan_validate(report, root, strict=strict)
    except Exception as exc:  # noqa: BLE001
        report["script_value_debrief"] = {
            "ok": True,
            "present": False,
            "warnings": [{"code": "DEBRIEF_CHECK_ERROR", "message": str(exc)[:200]}],
        }
    # Story quality overlay when graph exists
    if graph_path.is_file():
        try:
            from story_quality import check_story_quality

            graph = read_json(graph_path) or {}
            report["story_quality"] = check_story_quality(graph, root=root)
        except Exception as exc:  # noqa: BLE001
            report["story_quality"] = {"ok": True, "error": str(exc)[:160]}
    try:
        from story_structure import validate_story_structure

        graph = read_json(graph_path) if graph_path.is_file() else {}
        spec = read_json(root / "film-spec.json") or {}
        report["story_structure"] = validate_story_structure(
            graph if isinstance(graph, dict) else {},
            spec=spec if isinstance(spec, dict) else None,
            strict=False,
        )
    except Exception as exc:  # noqa: BLE001
        report["story_structure"] = {"ok": True, "error": str(exc)[:160]}
    return report, 0 if report.get("ok") else 1


def status(root: Path) -> tuple[dict[str, Any], int]:
    report = plan_status(root)
    return report, 0
