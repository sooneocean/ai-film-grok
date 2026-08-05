#!/usr/bin/env python3
"""CLI for MiniMax H3 film workflow (plan / run / list)."""

from __future__ import annotations

import argparse
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
        help="MiniMax H3 local motion lane (plan/run/list/next/run-next/pk-compare/pk-ledger)",
    )
    actions = parser.add_subparsers(dest="h3_action", required=True)

    plan = actions.add_parser("plan", help="Plan H3 execution for one shot")
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument("--shot-id", required=True)
    plan.add_argument("--receipt", type=Path, default=None)
    plan.add_argument(
        "--still",
        type=Path,
        default=None,
        help="Plan against an explicit still path (still-challenge candidate trial)",
    )
    plan.add_argument(
        "--last-frame",
        type=Path,
        default=None,
        dest="last_frame",
        help="End/last keyframe for first-last-frame (FLF) mode",
    )
    plan.add_argument(
        "--ref",
        type=Path,
        action="append",
        default=None,
        dest="refs",
        help="Optional reference image (repeatable; Phase 3 R2V multi-ref)",
    )

    run = actions.add_parser("run", help="Generate H3 clip for one shot on the 5090")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--shot-id", required=True)
    run.add_argument(
        "--mode",
        choices=["t2v", "i2v", "flf", "r2v"],
        default=None,
        help="t2v | i2v | flf (first+last on I2V weapon) | r2v",
    )
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
    run.add_argument(
        "--still",
        type=Path,
        default=None,
        help="Explicit still path override (pilot / still-challenge trial; does not auto-promote)",
    )
    run.add_argument(
        "--last-frame",
        type=Path,
        default=None,
        dest="last_frame",
        help="End/last keyframe for FLF (also auto from stills/<id>_end.png)",
    )
    run.add_argument(
        "--ref",
        type=Path,
        action="append",
        default=None,
        dest="refs",
        help="Optional reference image (repeatable)",
    )
    run.add_argument("--receipt", type=Path, default=None)

    lst = actions.add_parser(
        "list",
        help="List H3 jobs (primary restricted; --challenge adds Fill-Idle P2)",
    )
    lst.add_argument("--root", type=Path, required=True)
    lst.add_argument(
        "--challenge",
        action="store_true",
        help="Include P2 fill-idle challenges against existing baseline takes",
    )
    lst.add_argument(
        "--include-done",
        action="store_true",
        help="Keep shots already marked done in the list",
    )
    lst.add_argument("--receipt", type=Path, default=None)

    nxt = actions.add_parser(
        "next",
        help="Next Fill-Idle H3 command (P0→P1→P2 lowest-mean)",
    )
    nxt.add_argument("--root", type=Path, required=True)
    nxt.add_argument(
        "--no-challenge",
        action="store_true",
        help="Only primary restricted (skip soft P2 challenges)",
    )
    nxt.add_argument("--receipt", type=Path, default=None)

    run_next = actions.add_parser(
        "run-next",
        help="Fill-Idle worker: next job(s); --execute runs when capacity ready (not a daemon)",
    )
    run_next.add_argument("--root", type=Path, required=True)
    run_next.add_argument(
        "--execute",
        action="store_true",
        help="Actually run H3 when capacity ready",
    )
    run_next.add_argument(
        "--max",
        type=int,
        default=1,
        dest="max_jobs",
        help="Max jobs this call (default 1, hard cap 20) — still not a daemon",
    )
    run_next.add_argument(
        "--no-challenge",
        action="store_true",
        help="Skip P2 soft challenges",
    )
    run_next.add_argument(
        "--allow-without-capacity",
        action="store_true",
        help="Execute even when capacity probe is not ready",
    )
    run_next.add_argument("--no-register", action="store_true")
    run_next.add_argument(
        "--no-free-memory",
        action="store_true",
        help="Do not free Comfy VRAM when switching I2V/R2V/T2V mid-batch",
    )
    run_next.add_argument("--seed", type=int, default=20260804)
    run_next.add_argument("--timeout", type=int, default=1800)
    run_next.add_argument("--receipt", type=Path, default=None)

    pk = actions.add_parser(
        "pk-compare",
        help="Multi-take PK suggestion only (never auto-promote)",
    )
    pk.add_argument("--root", type=Path, required=True)
    pk.add_argument("--shot-id", default=None)
    pk.add_argument(
        "--measure",
        action="store_true",
        help="Measure missing mean_absdiff via ffmpeg (slower)",
    )
    pk.add_argument("--receipt", type=Path, default=None)

    ledger = actions.add_parser(
        "pk-ledger",
        help="Advisory PK dailies ledger (never promotes; no cross-film win-rate)",
    )
    ledger.add_argument("--root", type=Path, required=True)
    ledger.add_argument(
        "--append",
        action="store_true",
        help="Append a human winner decision",
    )
    ledger.add_argument("--shot-id", default=None)
    ledger.add_argument(
        "--winner",
        default=None,
        help="Winning take path (required with --append)",
    )
    ledger.add_argument("--lane", default=None, help="Winner lane hint (h3/grok/…)")
    ledger.add_argument("--mean", type=float, default=None)
    ledger.add_argument("--note", default="")
    ledger.add_argument("--receipt", type=Path, default=None)

    evidence = actions.add_parser(
        "evidence",
        help="Wave α · write fill-idle evidence metrics receipt (no GPU)",
    )
    evidence.add_argument("--root", type=Path, required=True)
    evidence.add_argument("--notes", default="")
    evidence.add_argument("--receipt", type=Path, default=None)

    cycle = actions.add_parser(
        "cycle",
        help="Fill-Idle cycle / overnight until-empty (never promote)",
    )
    cycle.add_argument("--root", type=Path, required=True)
    cycle.add_argument(
        "--execute",
        action="store_true",
        help="Actually run H3 jobs (default dry: only plan + evidence)",
    )
    cycle.add_argument("--max", type=int, default=5, dest="max_jobs")
    cycle.add_argument(
        "--until-empty",
        action="store_true",
        dest="until_empty",
        help="Loop cycles until queue empty / capacity block / fail (not an OS daemon)",
    )
    cycle.add_argument(
        "--max-cycles",
        type=int,
        default=40,
        dest="max_cycles",
        help="With --until-empty: max cycles (default 40, hard max 80)",
    )
    cycle.add_argument(
        "--continue-on-capacity",
        action="store_true",
        dest="continue_on_capacity",
        help="With --until-empty: do not stop when capacity not ready",
    )
    cycle.add_argument(
        "--free-first",
        action="store_true",
        dest="free_first",
        help=(
            "If Comfy queue is idle and only RAM/VRAM floors block, free models once "
            "before cycle/until-empty (never cancels foreign prompts)"
        ),
    )
    cycle.add_argument("--no-challenge", action="store_true")
    cycle.add_argument("--notes", default="")
    cycle.add_argument("--receipt", type=Path, default=None)

    cap = actions.add_parser(
        "capacity-plan",
        help="Backlog ETA by mode/priority (no GPU; writes receipts/h3-capacity-plan.json)",
    )
    cap.add_argument("--root", type=Path, required=True)
    cap.add_argument(
        "--no-challenge",
        action="store_true",
        help="Only primary H3 backlog (skip P2 soft challenges)",
    )
    cap.add_argument("--receipt", type=Path, default=None)

    combo = actions.add_parser("combo-eval", help="Idle-gated T2V/I2V/R2V(/FLF) combo grid")
    combo.add_argument("--root", type=Path, default=None)
    combo.add_argument("--still", type=Path, default=None)
    combo.add_argument("--end-still", type=Path, default=None, dest="end_still")
    combo.add_argument("--execute", action="store_true")
    combo.add_argument("--poll-sec", type=float, default=20.0, dest="poll_sec")
    combo.add_argument("--max-wait-sec", type=float, default=3600.0, dest="max_wait_sec")
    combo.add_argument("--no-free-memory", action="store_true")
    combo.add_argument("--write-registry", action="store_true", dest="write_registry")
    combo.add_argument("--round", type=int, default=1, dest="combo_round", help="1=baseline, 2=R2 optimized families")
    combo.add_argument("--seed", type=int, default=20260805)
    combo.add_argument("--receipt", type=Path, default=None)


def run_h3(args: argparse.Namespace) -> dict[str, Any]:
    action = str(args.h3_action)
    try:
        if action == "plan":
            report = plan_h3_shot(
                args.root,
                args.shot_id,
                still_override=getattr(args, "still", None),
                last_override=getattr(args, "last_frame", None),
                refs_override=getattr(args, "refs", None),
            )
        elif action == "list":
            report = list_h3_eligible_shots(
                args.root,
                include_challenge=bool(getattr(args, "challenge", False)),
                include_done=bool(getattr(args, "include_done", False)),
            )
        elif action == "next":
            from h3_fill_idle import next_fill_idle_job

            report = next_fill_idle_job(
                args.root,
                include_challenge=not bool(getattr(args, "no_challenge", False)),
            )
        elif action == "run-next":
            from h3_fill_idle import run_next_fill_idle

            report = run_next_fill_idle(
                args.root,
                include_challenge=not bool(getattr(args, "no_challenge", False)),
                execute=bool(getattr(args, "execute", False)),
                register=not bool(getattr(args, "no_register", False)),
                require_capacity=not bool(getattr(args, "allow_without_capacity", False)),
                seed=int(getattr(args, "seed", 20260804) or 20260804),
                timeout_sec=int(getattr(args, "timeout", 1800) or 1800),
                max_jobs=int(getattr(args, "max_jobs", 1) or 1),
                free_memory_on_mode_switch=not bool(getattr(args, "no_free_memory", False)),
            )
        elif action == "pk-ledger":
            from h3_fill_idle import append_pk_ledger, load_pk_ledger

            if getattr(args, "append", False):
                if not args.shot_id or not args.winner:
                    raise H3WorkflowError("pk-ledger --append needs --shot-id and --winner")
                report = append_pk_ledger(
                    args.root,
                    shot_id=str(args.shot_id),
                    winner_path=str(args.winner),
                    winner_lane=getattr(args, "lane", None),
                    mean=getattr(args, "mean", None),
                    note=str(getattr(args, "note", "") or ""),
                )
            else:
                report = load_pk_ledger(args.root)
        elif action == "pk-compare":
            from h3_fill_idle import pk_compare

            report = pk_compare(
                args.root,
                shot_id=getattr(args, "shot_id", None),
                measure_missing=bool(getattr(args, "measure", False)),
            )
        elif action == "evidence":
            from h3_fill_idle import write_fill_idle_evidence

            report = write_fill_idle_evidence(
                args.root,
                notes=str(getattr(args, "notes", "") or ""),
            )
        elif action == "cycle":
            from h3_fill_idle import fill_idle_cycle

            report = fill_idle_cycle(
                args.root,
                execute=bool(getattr(args, "execute", False)),
                max_jobs=int(getattr(args, "max_jobs", 5) or 5),
                include_challenge=not bool(getattr(args, "no_challenge", False)),
                notes=str(getattr(args, "notes", "") or ""),
                until_empty=bool(getattr(args, "until_empty", False)),
                max_cycles=int(getattr(args, "max_cycles", 40) or 40),
                stop_on_capacity=not bool(getattr(args, "continue_on_capacity", False)),
                free_first=bool(getattr(args, "free_first", False)),
            )
        elif action == "capacity-plan":
            from h3_fill_idle import capacity_plan

            report = capacity_plan(
                args.root,
                include_challenge=not bool(getattr(args, "no_challenge", False)),
            )
        elif action == "combo-eval":
            from datetime import datetime, timezone
            from h3_combo_eval import build_combo_matrix, prepare_eval_root, run_combo_grid, write_winners_registry
            skill_root = Path(__file__).resolve().parent.parent
            default_root = skill_root / "artifacts" / "5090-evaluation" / f"h3-combo-eval-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            eval_root = Path(args.root).expanduser().resolve() if args.root else default_root
            still = getattr(args, "still", None)
            if still is None:
                legacy = skill_root / "artifacts" / "5090-evaluation" / "h3-quality-ab-20260804" / "stills" / "s_ab.png"
                if legacy.is_file():
                    still = legacy
            combos = build_combo_matrix(seed=int(getattr(args, "seed", 20260805) or 20260805), round=int(getattr(args, "combo_round", 1) or 1))
            prepare_eval_root(eval_root, source_still=still, end_still=getattr(args, "end_still", None), combos=combos)
            report = run_combo_grid(
                eval_root, combos=combos,
                poll_sec=float(getattr(args, "poll_sec", 20.0) or 20.0),
                max_wait_per_job_sec=float(getattr(args, "max_wait_sec", 3600.0) or 3600.0),
                free_memory_on_mode_switch=not bool(getattr(args, "no_free_memory", False)),
                execute=bool(getattr(args, "execute", False)),
            )
            if bool(getattr(args, "write_registry", False)) and report.get("winners"):
                report["registry_path"] = str(write_winners_registry(report["winners"]))
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
                still_override=getattr(args, "still", None),
                last_override=getattr(args, "last_frame", None),
                refs_override=getattr(args, "refs", None),
            )
        else:
            raise H3WorkflowError(f"unknown h3 action: {action}")
    except H3WorkflowError as exc:
        return {"ok": False, "error": str(exc)}
    if getattr(args, "receipt", None):
        write_json(Path(args.receipt).expanduser().resolve(), report)
        report["receipt_path"] = str(Path(args.receipt).expanduser().resolve())
    return report
