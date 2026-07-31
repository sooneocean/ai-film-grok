"""CLI boundary for cloud-candidate orchestration; provider adapters submit separately."""

from __future__ import annotations

import argparse
from typing import Any

from interactive_orchestration import (
    InteractiveOrchestrationError,
    queue_status,
    record_task_failure,
    record_terminal_media,
    submit_cloud_candidate,
)


def add_interactive_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser("interactive", help="Track reviewable FRW/Grok cloud candidates")
    sub = parser.add_subparsers(dest="interactive_action", required=True)
    submit = sub.add_parser("submit", help="Record an adapter-submitted cloud task")
    submit.add_argument("--root", required=True)
    submit.add_argument("--candidate-id", required=True)
    submit.add_argument("--shot-id", required=True)
    submit.add_argument("--capability-id", required=True)
    submit.add_argument("--task-id", required=True)
    terminal = sub.add_parser("terminal", help="Bind staged decoded cloud media for review")
    terminal.add_argument("--root", required=True)
    terminal.add_argument("--candidate-id", required=True)
    terminal.add_argument("--media-path", required=True)
    failed = sub.add_parser("failed", help="Retain a stable cloud task failure")
    failed.add_argument("--root", required=True)
    failed.add_argument("--candidate-id", required=True)
    failed.add_argument("--error-code", required=True)
    status = sub.add_parser("status")
    status.add_argument("--root", required=True)


def run_interactive(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    try:
        if args.interactive_action == "submit":
            return submit_cloud_candidate(
                args.root,
                candidate_id=args.candidate_id,
                shot_id=args.shot_id,
                capability_id=args.capability_id,
                task_id=args.task_id,
            ), 0
        if args.interactive_action == "terminal":
            return record_terminal_media(
                args.root, candidate_id=args.candidate_id, media_path=args.media_path
            ), 0
        if args.interactive_action == "failed":
            return record_task_failure(
                args.root, candidate_id=args.candidate_id, error_code=args.error_code
            ), 0
        if args.interactive_action == "status":
            return queue_status(args.root), 0
    except InteractiveOrchestrationError as exc:
        return {"ok": False, "error": str(exc)}, 2
    return {"ok": False, "error": "unknown interactive action"}, 2
