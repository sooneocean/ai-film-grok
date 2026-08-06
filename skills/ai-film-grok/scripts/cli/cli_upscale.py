"""CLI: aifilm upscale — Real-ESRGAN formal upscale after selects."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from realesrgan_upscale import (
    UpscaleError,
    plan_upscale,
    promote_upscale,
    run_canary_ab,
    run_upscale_batch,
)
from util import write_json


def add_upscale_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "upscale",
        help="Real-ESRGAN formal upscale (selects-after; default off; no auto-promote)",
    )
    actions = parser.add_subparsers(dest="upscale_action", required=True)

    plan = actions.add_parser("plan", help="List upscale candidates (read-only)")
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument(
        "--all-takes",
        action="store_true",
        help="Include takes/ tree (default: manifest preferred only)",
    )
    plan.add_argument(
        "--include-at-floor",
        action="store_true",
        help="Include clips already ≥704×1280",
    )
    plan.add_argument("--path", action="append", default=None, help="Explicit media path(s)")
    plan.add_argument("--receipt", type=Path, default=None)

    run = actions.add_parser("run", help="Dry-run or --execute upscale (no promote)")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--path", action="append", default=None)
    run.add_argument("--shot-id", action="append", default=None)
    run.add_argument("--max", type=int, default=1, dest="max_items")
    run.add_argument("--model", default="realesr-animevideov3")
    run.add_argument("--scale", type=int, default=2, choices=[1, 2, 3, 4])
    run.add_argument("--target-width", type=int, default=704)
    run.add_argument("--target-height", type=int, default=1280)
    run.add_argument("--all-takes", action="store_true")
    run.add_argument("--include-at-floor", action="store_true")
    run.add_argument("--execute", action="store_true")
    run.add_argument(
        "--i-own-the-gpu",
        action="store_true",
        help="Bypass soft GPU busy/lease skip (explicit owner)",
    )
    run.add_argument("--receipt", type=Path, default=None)

    promote = actions.add_parser(
        "promote",
        help="Human promote upscale output into takes/<shot>/ (does not auto register-clip)",
    )
    promote.add_argument("--root", type=Path, required=True)
    promote.add_argument("--shot-id", required=True)
    promote.add_argument("--source", type=Path, default=None)
    promote.add_argument("--note", default="")
    promote.add_argument("--receipt", type=Path, default=None)

    canary = actions.add_parser(
        "canary",
        help="A/B canary: ffmpeg geometry vs Real-ESRGAN on one source",
    )
    canary.add_argument("--source", type=Path, required=True)
    canary.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: skills/.../artifacts/realesrgan-canary",
    )
    canary.add_argument("--scale", type=int, default=2, choices=[1, 2, 3, 4])
    canary.add_argument("--model", default="realesr-animevideov3")
    canary.add_argument("--receipt", type=Path, default=None)


def run_upscale_cli(args: argparse.Namespace) -> dict[str, Any]:
    action = str(args.upscale_action)
    try:
        if action == "plan":
            report = plan_upscale(
                args.root,
                preferred_only=not bool(getattr(args, "all_takes", False)),
                include_at_floor=bool(getattr(args, "include_at_floor", False)),
                paths=getattr(args, "path", None),
            )
        elif action == "run":
            if getattr(args, "i_own_the_gpu", False):
                import os

                os.environ["AIFILM_I_OWN_THE_GPU"] = "1"
            report = run_upscale_batch(
                args.root,
                paths=getattr(args, "path", None),
                shot_ids=getattr(args, "shot_id", None),
                max_items=int(getattr(args, "max_items", 1) or 1),
                model=str(getattr(args, "model", "realesr-animevideov3")),
                scale=int(getattr(args, "scale", 2) or 2),
                target_width=int(getattr(args, "target_width", 704) or 704),
                target_height=int(getattr(args, "target_height", 1280) or 1280),
                preferred_only=not bool(getattr(args, "all_takes", False)),
                include_at_floor=bool(getattr(args, "include_at_floor", False)),
                execute=bool(getattr(args, "execute", False)),
                force_gpu=bool(getattr(args, "i_own_the_gpu", False)),
            )
        elif action == "promote":
            report = promote_upscale(
                args.root,
                shot_id=str(args.shot_id),
                source=getattr(args, "source", None),
                note=str(getattr(args, "note", "") or ""),
            )
        elif action == "canary":
            skill_art = (
                Path(__file__).resolve().parents[2] / "artifacts" / "realesrgan-canary"
            )
            out_dir = getattr(args, "out_dir", None) or skill_art
            report = run_canary_ab(
                args.source,
                out_dir,
                scale=int(getattr(args, "scale", 2) or 2),
                model=str(getattr(args, "model", "realesr-animevideov3")),
            )
        else:
            raise UpscaleError(f"unknown upscale action: {action}")
    except UpscaleError as exc:
        report = {"ok": False, "error": str(exc), "kind": "ai-film-upscale-error"}

    receipt = getattr(args, "receipt", None)
    if receipt:
        write_json(Path(receipt), report)
        report = {**report, "receipt_path": str(Path(receipt).expanduser().resolve())}
    return report
