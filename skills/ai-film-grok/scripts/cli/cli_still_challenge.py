"""CLI: aifilm still-challenge — FRW i2i material challenge for I2V/R2V sources."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from still_challenge import (
    StillChallengeError,
    build_still_challenge_queue,
    list_candidates,
    next_still_challenge_job,
    promote_still_challenge,
    run_still_challenge,
)
from util import write_json


def add_still_challenge_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "still-challenge",
        help="FRW img2image still challenge (≥30s/unit) to improve I2V/R2V source materials",
    )
    actions = parser.add_subparsers(dest="still_challenge_action", required=True)

    plan = actions.add_parser("plan", help="List still-challenge queue (read-only)")
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument("--include-done", action="store_true")
    plan.add_argument("--receipt", type=Path, default=None)

    nxt = actions.add_parser("next", help="Next 1-unit still-challenge job + rate window")
    nxt.add_argument("--root", type=Path, required=True)
    nxt.add_argument("--receipt", type=Path, default=None)

    lst = actions.add_parser("list", help="List FRW still candidates for a shot or whole film")
    lst.add_argument("--root", type=Path, required=True)
    lst.add_argument("--shot-id", default=None)
    lst.add_argument("--receipt", type=Path, default=None)

    run = actions.add_parser("run", help="Dry-run or --execute one FRW img2image unit")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--shot-id", required=True)
    run.add_argument("--source", type=Path, default=None)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--max-submits", type=int, default=1)
    run.add_argument("--model", default="flux")
    run.add_argument("--seed", type=int, default=20260804)
    run.add_argument("--prompt", default=None)
    run.add_argument(
        "--skip-capability-gate",
        action="store_true",
        help="Only for tests / explicit override when canary is proven offline",
    )
    run.add_argument("--receipt", type=Path, default=None)

    promote = actions.add_parser(
        "promote",
        help="Human promote candidate still → stills/ (required identity gates for approved)",
    )
    promote.add_argument("--root", type=Path, required=True)
    promote.add_argument("--shot-id", required=True)
    promote.add_argument("--source", type=Path, default=None)
    promote.add_argument("--status", default="approved", choices=["approved", "candidate"])
    promote.add_argument("--identity-approved", action="store_true")
    promote.add_argument("--anatomy-safe", action="store_true")
    promote.add_argument("--review-note", default="")
    promote.add_argument(
        "--as",
        dest="as_role",
        default="first",
        choices=["first", "end"],
        help="Promote as start still (first) or FLF end still (end → stills/<id>_end.png)",
    )
    promote.add_argument("--receipt", type=Path, default=None)


def run_still_challenge_cli(args: argparse.Namespace) -> dict[str, Any]:
    action = str(args.still_challenge_action)
    try:
        if action == "plan":
            report = build_still_challenge_queue(
                args.root,
                include_done=bool(getattr(args, "include_done", False)),
            )
        elif action == "next":
            report = next_still_challenge_job(args.root)
        elif action == "list":
            root = Path(args.root).expanduser().resolve()
            sid = getattr(args, "shot_id", None)
            if sid:
                report = {
                    "ok": True,
                    "kind": "ai-film-still-challenge-list",
                    "shot_id": sid,
                    "candidates": list_candidates(root, str(sid)),
                }
            else:
                q = build_still_challenge_queue(root, include_done=True)
                report = {
                    "ok": True,
                    "kind": "ai-film-still-challenge-list",
                    "root": str(root),
                    "rows": [
                        {
                            "shot_id": r.get("shot_id"),
                            "priority": r.get("priority"),
                            "status": r.get("status"),
                            "candidates": r.get("candidates"),
                        }
                        for r in (q.get("rows") or [])
                    ],
                }
        elif action == "run":
            report = run_still_challenge(
                args.root,
                str(args.shot_id),
                source=getattr(args, "source", None),
                execute=bool(getattr(args, "execute", False)),
                max_submits=int(getattr(args, "max_submits", 1) or 1),
                model=str(getattr(args, "model", None) or "flux"),
                seed=int(getattr(args, "seed", 20260804) or 20260804),
                prompt=getattr(args, "prompt", None),
                skip_capability_gate=bool(getattr(args, "skip_capability_gate", False)),
            )
        elif action == "promote":
            report = promote_still_challenge(
                args.root,
                str(args.shot_id),
                source=getattr(args, "source", None),
                identity_approved=bool(getattr(args, "identity_approved", False)),
                anatomy_safe=bool(getattr(args, "anatomy_safe", False)),
                review_note=str(getattr(args, "review_note", "") or ""),
                status=str(getattr(args, "status", "approved") or "approved"),
                as_role=str(getattr(args, "as_role", "first") or "first"),
            )
        else:
            raise StillChallengeError(f"unknown still-challenge action: {action}")
    except StillChallengeError as exc:
        return {"ok": False, "error": str(exc)}
    if getattr(args, "receipt", None):
        path = Path(args.receipt).expanduser().resolve()
        write_json(path, report)
        report["receipt_path"] = str(path)
    return report
