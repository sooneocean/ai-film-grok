"""Director/department/serial CLI — extracted from aifilm_grok (public cmd strings unchanged).

Uses scripts/core for film IO/emit/gates (no hub cycle for basic IO).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from util.errors import FilmError


def add_director_ops_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    director_p = sub.add_parser(
        "director",
        help=(
            "Production book: init|migrate-audit|migrate|status|check|lock-stage|"
            "impact|rebuild|verify|interpret-scene"
        ),
    )
    director_sub = director_p.add_subparsers(dest="director_action", required=True)
    d_init = director_sub.add_parser("init")
    d_init.add_argument("--root", required=True)
    d_init.add_argument("--title", default="Untitled")
    d_init.add_argument(
        "--rigor", choices=("legacy", "guided", "professional"), default="professional"
    )
    d_init.add_argument("--format-pack", default="vertical-short")
    d_init.add_argument("--genre-pack", default="drama")
    d_init.add_argument(
        "--quality-target",
        choices=("standard", "premium_vertical"),
        default=None,
        help="Creative quality gate profile; legacy projects default to standard",
    )
    d_migrate_audit = director_sub.add_parser("migrate-audit")
    d_migrate_audit.add_argument("--root", required=True)
    d_migrate = director_sub.add_parser("migrate")
    d_migrate.add_argument("--root", required=True)
    d_migrate.add_argument("--title", default="Untitled")
    for director_action in ("status", "check", "verify"):
        action_parser = director_sub.add_parser(director_action)
        action_parser.add_argument("--root", required=True)

    serial_p = sub.add_parser("serial", help="Optional serial-drama narrative and safety gates")
    serial_sub = serial_p.add_subparsers(dest="serial_action", required=True)
    serial_validate = serial_sub.add_parser(
        "validate", help="Validate serial contract and write receipt"
    )
    serial_validate.add_argument("--root", required=True)
    d_lock_stage = director_sub.add_parser(
        "lock-stage",
        help="Human-approve and hash-lock the current stage over native evidence",
    )
    d_lock_stage.add_argument("--root", required=True)
    d_lock_stage.add_argument(
        "--stage",
        required=True,
        choices=(
            "concept_lock",
            "script_lock",
            "department_look_lock",
            "shot_animatic_lock",
            "pilot_approval",
            "bulk",
            "dailies_review",
            "selects_rough_cut",
            "picture_lock",
            "post_locks",
            "master_lock",
        ),
    )
    d_lock_stage.add_argument("--approver", default="user")
    lock_authorization = d_lock_stage.add_mutually_exclusive_group(required=True)
    lock_authorization.add_argument("--user-phrase")
    lock_authorization.add_argument("--authorization-event")
    d_lock_stage.add_argument(
        "--input-ref",
        action="append",
        default=[],
        metavar="NAME=RELATIVE_PATH",
        help="Override auto-resolved native evidence; repeat for multiple refs",
    )
    d_lock_stage.add_argument("--transaction-id", default=None)
    for director_action in ("impact", "rebuild"):
        action_parser = director_sub.add_parser(director_action)
        action_parser.add_argument("--root", required=True)
        action_parser.add_argument("--changed-ref", action="append", required=True)
        action_parser.add_argument("--reason", required=True)
        if director_action == "rebuild":
            action_parser.add_argument("--expected-revision", type=int, required=True)
            action_parser.add_argument("--transaction-id", default=None)

    d_interpret = director_sub.add_parser(
        "interpret-scene",
        help="Director Interpretation receipt before shot list (Film Production OS W2)",
    )
    d_interpret.add_argument("--root", required=True)
    d_interpret.add_argument("--scene-id", default=None, help="Scene id; default first scene")

    department_p = sub.add_parser(
        "department",
        help="Department bibles: list|show|edit|diff|handoff|validate|lock|unlock|status",
    )
    department_sub = department_p.add_subparsers(dest="department_action", required=True)
    dept_list = department_sub.add_parser("list")
    dept_list.add_argument("--root", required=True)
    for department_action in ("show", "validate", "status"):
        action_parser = department_sub.add_parser(department_action)
        action_parser.add_argument("--root", required=True)
        action_parser.add_argument("--id", dest="department_id", required=True)
    dept_edit = department_sub.add_parser("edit")
    dept_edit.add_argument("--root", required=True)
    dept_edit.add_argument("--id", dest="department_id", required=True)
    dept_edit.add_argument("--payload-file", required=True)
    dept_edit.add_argument("--expected-revision", type=int, required=True)
    dept_edit.add_argument("--dry-run", action="store_true")
    dept_diff = department_sub.add_parser("diff")
    dept_diff.add_argument("--root", required=True)
    dept_diff.add_argument("--id", dest="department_id", required=True)
    dept_diff.add_argument("--payload-file", required=True)
    dept_handoff = department_sub.add_parser(
        "handoff", help="Verify immutable upstream bibles before a department starts work"
    )
    dept_handoff.add_argument("--root", required=True)
    dept_handoff.add_argument("--to", dest="department_id", required=True)
    dept_lock = department_sub.add_parser("lock")
    dept_lock.add_argument("--root", required=True)
    dept_lock.add_argument("--id", dest="department_id", required=True)
    dept_lock.add_argument("--approval-ref", required=True)
    dept_lock.add_argument("--expected-revision", type=int, required=True)
    dept_unlock = department_sub.add_parser("unlock")
    dept_unlock.add_argument("--root", required=True)
    dept_unlock.add_argument("--id", dest="department_id", required=True)
    dept_unlock.add_argument("--reason", required=True)
    dept_unlock.add_argument("--expected-revision", type=int, required=True)

    dn = sub.add_parser(
        "director-notes",
        help="List/add/resolve director reshoot notes (scorecard fail loop)",
    )
    dn_sub = dn.add_subparsers(dest="notes_cmd", required=True)
    dn_list = dn_sub.add_parser("list", help="Show open and all reshoot items")
    dn_list.add_argument("--root", required=True)
    dn_add = dn_sub.add_parser("add", help="Add a reshoot/recut item")
    dn_add.add_argument("--root", required=True)
    dn_add.add_argument("--action", required=True, choices=["keep", "reshoot", "recut"])
    dn_add.add_argument(
        "--reason",
        required=True,
        choices=[
            "identity",
            "style",
            "motion",
            "escalation",
            "audio",
            "subs",
            "dead_air",
            "other",
            "continuity",
            "performance",
        ],
    )
    dn_add.add_argument("--shot-id", default=None)
    dn_add.add_argument("--note", default="")
    dn_res = dn_sub.add_parser("resolve", help="Mark open item(s) resolved")
    dn_res.add_argument("--root", required=True)
    dn_res.add_argument("--item-id", default=None)
    dn_res.add_argument("--shot-id", default=None)
    dn_res.add_argument("--note", default="")

def cmd_director(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from director_cli import (
        check,
        director_init,
        impact,
        lock_native_stage,
        migrate,
        migrate_audit,
        rebuild,
        status,
        verify,
    )

    root = Path(args.root).expanduser().resolve()
    action = args.director_action
    try:
        if action == "init":
            report = director_init(
                root,
                title=args.title,
                rigor=args.rigor,
                format_pack=args.format_pack,
                genre_pack=args.genre_pack,
                quality_target=args.quality_target,
            )
        elif action == "migrate-audit":
            report = migrate_audit(root)
        elif action == "migrate":
            report = migrate(root, title=args.title)
        elif action == "status":
            report = status(root)
        elif action == "check":
            report = check(root)
        elif action == "lock-stage":
            input_refs: dict[str, str] | None = None
            if args.input_ref:
                input_refs = {}
                for item in args.input_ref:
                    name, separator, relative = str(item).partition("=")
                    if not separator or not name.strip() or not relative.strip():
                        raise FilmError("--input-ref must use NAME=RELATIVE_PATH")
                    input_refs[name.strip()] = relative.strip()
            report = lock_native_stage(
                root,
                stage=args.stage,
                approver=args.approver,
                user_phrase=args.user_phrase,
                authorization_event=args.authorization_event,
                input_refs=input_refs,
                transaction_id=args.transaction_id,
            )
        elif action == "impact":
            report = impact(root, changed_refs=args.changed_ref, reason=args.reason)
        elif action == "rebuild":
            report = rebuild(
                root,
                changed_refs=args.changed_ref,
                reason=args.reason,
                expected_revision=args.expected_revision,
                transaction_id=args.transaction_id,
            )
        elif action == "verify":
            report = verify(root)
        elif action == "interpret-scene":
            from director_interpretation import interpret_scene_at_root

            report = interpret_scene_at_root(root, scene_id=getattr(args, "scene_id", None))
        else:
            raise FilmError(f"unknown director action {action!r}")
    except (OSError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 1


def cmd_serial(args: argparse.Namespace) -> int:
    """Run the optional serial-production contract validator."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from serial_quality import validate_serial

    if args.serial_action != "validate":
        raise FilmError(f"unknown serial action {args.serial_action!r}")
    report = validate_serial(Path(args.root).expanduser().resolve(), write_receipt=True)
    emit(report)
    return 0 if report.get("ok") else 1


def cmd_department(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from department_cli import (
        diff_department,
        edit_department,
        handoff_department,
        list_departments,
        lock_department,
        show_department,
        unlock_department,
        validate_department,
    )

    root = Path(args.root).expanduser().resolve()
    action = args.department_action
    try:
        if action == "list":
            report = list_departments(root)
        elif action in {"show", "status"}:
            report = show_department(root, args.department_id)
        elif action == "edit":
            report = edit_department(
                root,
                args.department_id,
                payload_file=args.payload_file,
                expected_revision=args.expected_revision,
                dry_run=args.dry_run,
            )
        elif action == "diff":
            report = diff_department(root, args.department_id, payload_file=args.payload_file)
        elif action == "handoff":
            report = handoff_department(root, args.department_id)
        elif action == "validate":
            report = validate_department(root, args.department_id)
        elif action == "lock":
            report = lock_department(
                root,
                args.department_id,
                approval_ref=args.approval_ref,
                expected_revision=args.expected_revision,
            )
        elif action == "unlock":
            report = unlock_department(
                root,
                args.department_id,
                reason=args.reason,
                expected_revision=args.expected_revision,
            )
        else:
            raise FilmError(f"unknown department action {action!r}")
    except (OSError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 1


def cmd_director_notes(args: argparse.Namespace) -> int:
    """List / add / resolve director reshoot notes (B3 closed loop)."""
    from core.emit import emit
    from core.film_io import (
        director_notes_path,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates
    from director_review import (
        DirectorReviewError,
        add_reshoot_item,
        open_reshoot_items,
        reshoots_clear,
        resolve_reshoot_item,
    )

    root = Path(args.root).expanduser().resolve()
    load_manifest(root)  # ensures project exists
    action = args.notes_cmd
    package = load_director_notes(root)

    if action == "list":
        open_items = open_reshoot_items(package)
        emit(
            {
                "ok": True,
                "path": str(director_notes_path(root))
                if director_notes_path(root).is_file()
                else None,
                "open_reshoot_count": len(open_items),
                "open_reshoots": open_items,
                "items": package.get("items") or [],
                "reshoots_clear": reshoots_clear(package),
                "scorecard": package.get("scorecard"),
            }
        )
        return 0

    if action == "add":
        try:
            item = add_reshoot_item(
                package,
                action=str(args.action),
                reason_code=str(args.reason),
                note=str(args.note or ""),
                shot_id=(str(args.shot_id).strip() if args.shot_id else None),
                source="manual",
            )
        except DirectorReviewError as exc:
            raise FilmError(str(exc)) from exc
        path = save_director_notes(root, package)
        manifest = load_manifest(root)
        recompute_gates(root, manifest)
        save_manifest(root, manifest)
        emit(
            {
                "ok": True,
                "path": str(path),
                "item": item,
                "open_reshoot_count": len(open_reshoot_items(package)),
            }
        )
        return 0

    if action == "resolve":
        try:
            resolved = resolve_reshoot_item(
                package,
                item_id=(str(args.item_id).strip() if args.item_id else None),
                shot_id=(str(args.shot_id).strip() if args.shot_id else None),
                resolve_note=str(args.note or ""),
            )
        except DirectorReviewError as exc:
            raise FilmError(str(exc)) from exc
        path = save_director_notes(root, package)
        manifest = load_manifest(root)
        recompute_gates(root, manifest)
        save_manifest(root, manifest)
        emit(
            {
                "ok": True,
                "path": str(path),
                "resolved": resolved,
                "open_reshoot_count": len(open_reshoot_items(package)),
                "reshoots_clear": reshoots_clear(package),
            }
        )
        return 0

    raise FilmError(f"Unknown director-notes action: {action}")

