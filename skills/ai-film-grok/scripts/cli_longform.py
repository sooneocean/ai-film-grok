"""CLI routes for the bounded longform production mode."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from longform import LongformError, longform_status, prepare_longform_resume


def add_longform_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "longform", help="8–15 minute vertical longform status and bounded resume"
    )
    actions = parser.add_subparsers(dest="longform_action", required=True)
    status = actions.add_parser("status", help="Read the longform plan without changing state")
    status.add_argument("--root", required=True)
    status.set_defaults(no_write=True)
    resume = actions.add_parser(
        "resume", help="Verify one unit and return its bounded resume action"
    )
    resume.add_argument("--root", required=True)
    resume.add_argument("--unit", required=True)
    resume.set_defaults(no_write=True)


def cmd_longform(args: Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    try:
        if args.longform_action == "status":
            from aifilm_grok import emit

            report = longform_status(root)
            emit(report)
            return 0 if report.get("ok") else 1
        if args.longform_action == "resume":
            from aifilm_grok import emit

            report = prepare_longform_resume(root, unit_id=str(args.unit))
            emit(report)
            return 0
    except LongformError as exc:
        from aifilm_grok import FilmError

        raise FilmError(str(exc)) from exc
    raise ValueError(f"unknown longform action: {args.longform_action}")
