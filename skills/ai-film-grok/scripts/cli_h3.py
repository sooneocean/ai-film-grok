#!/usr/bin/env python3
"""CLI for MiniMax H3 film workflow (plan / run / list)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from h3_workflow import (
    H3WorkflowError,
    list_h3_eligible_shots,
    plan_h3_shot,
    run_h3_shot,
)
from util import write_json


def add_h3_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "h3",
        help="MiniMax H3 local motion lane (plan/run/list for hybrid_h3 films)",
    )
    actions = parser.add_subparsers(dest="h3_action", required=True)

    plan = actions.add_parser("plan", help="Plan H3 execution for one shot")
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument("--shot-id", required=True)
    plan.add_argument("--receipt", type=Path, default=None)

    run = actions.add_parser("run", help="Generate H3 clip for one shot on the 5090")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--shot-id", required=True)
    run.add_argument("--mode", choices=["t2v", "i2v", "r2v"], default=None)
    run.add_argument("--register", action="store_true")
    run.add_argument("--status", default="candidate", choices=["candidate", "approved", "rejected"])
    run.add_argument(
        "--allow-experimental",
        action="store_true",
        default=False,
        help="Only needed for non-promoted experimental weapons (H3 film-lane is production)",
    )
    run.add_argument(
        "--stage",
        choices=["production", "pilot"],
        default="production",
        help="Armory execution stage (default production for promoted H3 film-lane)",
    )
    run.add_argument("--seed", type=int, default=20260803)
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--no-queue", action="store_true")
    run.add_argument("--receipt", type=Path, default=None)

    lst = actions.add_parser("list", help="List shots that route to comfy-h3")
    lst.add_argument("--root", type=Path, required=True)
    lst.add_argument("--receipt", type=Path, default=None)


def run_h3(args: argparse.Namespace) -> dict[str, Any]:
    action = str(args.h3_action)
    try:
        if action == "plan":
            report = plan_h3_shot(args.root, args.shot_id)
        elif action == "list":
            report = list_h3_eligible_shots(args.root)
        elif action == "run":
            report = run_h3_shot(
                args.root,
                args.shot_id,
                mode=args.mode,
                register=bool(args.register),
                status=str(args.status),
                allow_experimental=bool(args.allow_experimental) or None,
                seed=int(args.seed),
                timeout_sec=int(args.timeout),
                enqueue_queue=not bool(args.no_queue),
                production_stage=str(getattr(args, "stage", None) or "production"),
            )
        else:
            raise H3WorkflowError(f"unknown h3 action: {action}")
    except H3WorkflowError as exc:
        return {"ok": False, "error": str(exc)}
    if getattr(args, "receipt", None):
        write_json(Path(args.receipt).expanduser().resolve(), report)
        report["receipt_path"] = str(Path(args.receipt).expanduser().resolve())
    return report
