"""Quality/heat/dialogue gates CLI — extracted from aifilm_grok (public cmd strings unchanged).

Uses scripts/core for film IO/emit/gates (no hub cycle for basic IO).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from util.errors import FilmError


def add_quality_ops_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    heat_p = sub.add_parser(
        "heat",
        help="Adult heat: check | vo-suggest | boost | soften-log | soften-compensate",
    )
    heat_sub = heat_p.add_subparsers(dest="heat_action", required=True)
    heat_ck = heat_sub.add_parser(
        "check",
        help="One-page heat report (duration/wardrobe/VO/coitus/size/pose/montage)",
    )
    heat_ck.add_argument("--root", required=True)
    heat_vo = heat_sub.add_parser(
        "vo-suggest",
        help="Suggest denser adult nar lines by heat_phase/coitus_beat",
    )
    heat_vo.add_argument("--root", required=True)
    heat_vo.add_argument("--shot", default=None, help="Optional shot id")
    heat_boost_p = heat_sub.add_parser(
        "boost",
        help="Impact S boost plan; --apply patches duration/bare/detail/verbs/VO (never lower heat)",
    )
    heat_boost_p.add_argument("--root", required=True)
    heat_boost_p.add_argument(
        "--apply",
        action="store_true",
        help="Write field patches into film-spec + receipts/heat-boost.json",
    )
    heat_boost_p.add_argument(
        "--target-score",
        type=float,
        default=90.0,
        help="Target erotic impact score (default 90 = grade S)",
    )
    heat_sf = heat_sub.add_parser(
        "soften-log",
        help="Write receipts/moderation_soften.json dual-track compensation (never lower heat)",
    )
    heat_sf.add_argument("--root", required=True)
    heat_sf.add_argument("--note", default="", help="What was soft-moderated")
    heat_sc = heat_sub.add_parser(
        "soften-compensate",
        help="Dual-track compensate: checklist + optional --apply VO/SFX/music_energy (never lower heat)",
    )
    heat_sc.add_argument("--root", required=True)
    heat_sc.add_argument("--note", default="", help="What was soft-moderated")
    heat_sc.add_argument(
        "--apply",
        action="store_true",
        help="Write VO spice + sex SFX + music_energy into film-spec (still no still gen)",
    )

    pf = sub.add_parser(
        "preflight",
        help="Lesson-based health check before bulk/final (hard+soft)",
    )
    pf.add_argument("--root", required=True)
    pf.add_argument("--strict", action="store_true", help="Also fail on soft warnings")

    cinematic = sub.add_parser(
        "cinematic-audit",
        help="Write a checksum-bound cinematic coherence/coverage audit (no-spend)",
    )
    cinematic.add_argument("--root", required=True)

    quality = sub.add_parser(
        "quality", help="Read persisted per-shot quality receipts (no media scan)"
    )
    quality.add_argument("--root", required=True)
    quality.add_argument("--shot-id", default=None)

    takes_p = sub.add_parser(
        "takes",
        help="Take compare / director review (Film Production OS W5)",
    )
    takes_sub = takes_p.add_subparsers(dest="takes_action", required=True)
    takes_compare = takes_sub.add_parser("compare", help="Compare takes for one shot")
    takes_compare.add_argument("--root", required=True)
    takes_compare.add_argument("--shot-id", required=True)
    takes_review = takes_sub.add_parser(
        "review",
        help="Attach director_review scores / director_status (never overwrite media)",
    )
    takes_review.add_argument("--root", required=True)
    takes_review.add_argument("--shot-id", required=True)
    takes_review.add_argument("--take-id", default=None)
    takes_review.add_argument("--performance", type=int, default=None)
    takes_review.add_argument("--continuity", type=int, default=None)
    takes_review.add_argument("--camera", type=int, default=None)
    takes_review.add_argument("--artifacts", type=int, default=None)
    takes_review.add_argument(
        "--director-status",
        default=None,
        choices=(
            "generated",
            "candidate",
            "selected",
            "approved",
            "rejected",
            "archived",
            "active",
        ),
    )

    benchmark_p = sub.add_parser(
        "benchmark", help="Run a no-spend premium vertical benchmark contract"
    )
    benchmark_p.add_argument("--root", default=None, help="Optional film root for receipt binding")
    benchmark_p.add_argument("--suite", choices=("premium-vertical",), default="premium-vertical")
    benchmark_p.add_argument("--mode", choices=("contract", "live"), default="contract")

    dialogue_benchmark_p = sub.add_parser(
        "dialogue-benchmark",
        help="Plan the 30–60s Qwen/keyframe/FRW-LTX benchmark without spending",
    )
    dialogue_benchmark_p.add_argument("--root", required=True)

    dialogue_benchmark_review_p = sub.add_parser(
        "dialogue-benchmark-review", help="Record a human-reviewed Qwen/keyframe/FRW-LTX arm"
    )
    dialogue_benchmark_review_p.add_argument("--root", required=True)
    dialogue_benchmark_review_p.add_argument("--weapon", required=True)
    dialogue_benchmark_review_p.add_argument("--artifact", required=True)
    dialogue_benchmark_review_p.add_argument("--reviewer", required=True)
    dialogue_benchmark_review_p.add_argument("--note", required=True)
    dialogue_benchmark_review_p.add_argument("--parameters-json", required=True)

    dialogue_benchmark_approve_p = sub.add_parser(
        "dialogue-benchmark-approve", help="Approve all reviewed dialogue benchmark parameters"
    )
    dialogue_benchmark_approve_p.add_argument("--root", required=True)
    dialogue_benchmark_approve_p.add_argument("--reviewer", required=True)
    dialogue_benchmark_approve_p.add_argument("--rationale", required=True)

    dialogue_production_plan_p = sub.add_parser(
        "dialogue-production-plan",
        help="Compile the no-spend Qwen/keyframe/FRW-LTX/LatentSync-fallback dialogue plan",
    )
    dialogue_production_plan_p.add_argument("--root", required=True)

    dialogue_benchmark_queue_p = sub.add_parser(
        "dialogue-benchmark-queue",
        help="Persist/claim the no-submit P2 Qwen/Wan/LatentSync benchmark queue",
    )
    dialogue_benchmark_queue_sub = dialogue_benchmark_queue_p.add_subparsers(
        dest="dialogue_benchmark_queue_action", required=True
    )
    for queue_action in ("enqueue", "claim", "status"):
        item = dialogue_benchmark_queue_sub.add_parser(queue_action)
        item.add_argument("--root", required=True)
    dialogue_benchmark_queue_complete_p = dialogue_benchmark_queue_sub.add_parser("complete")
    dialogue_benchmark_queue_complete_p.add_argument("--root", required=True)
    dialogue_benchmark_queue_complete_p.add_argument("--job-id", required=True)
    dialogue_benchmark_queue_complete_p.add_argument("--claim-token", required=True)
    dialogue_benchmark_queue_submit_p = dialogue_benchmark_queue_sub.add_parser("submit-comfy")
    dialogue_benchmark_queue_submit_p.add_argument("--root", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--job-id", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--claim-token", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--workflow", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--weapon-id", required=True)

    creative = sub.add_parser(
        "creative-pipeline", help="Radio cut, animatic and premium pre-production gates"
    )
    creative_sub = creative.add_subparsers(dest="pipeline_action", required=True)
    cr = creative_sub.add_parser("readiness")
    cr.add_argument("--root", required=True)
    radio = creative_sub.add_parser("radio-cut")
    radio.add_argument("--root", required=True)
    radio.add_argument("--write", action="store_true")
    radio.add_argument("--timing-ok", action="store_true")
    radio.add_argument("--emotion-turns-ok", action="store_true")
    radio.add_argument("--shot-count", type=int, default=0)
    anim = creative_sub.add_parser("animatic")
    anim.add_argument("--root", required=True)
    anim.add_argument("--write", action="store_true")
    anim.add_argument("--coverage-ok", action="store_true")
    anim.add_argument("--pace-ok", action="store_true")
    anim.add_argument("--performance-ok", action="store_true")

    dailies = sub.add_parser(
        "dailies", help="Record and audit Select/Alternate/Reject/Reshoot candidates"
    )
    dailies_sub = dailies.add_subparsers(dest="dailies_action", required=True)
    ds = dailies_sub.add_parser("status")
    ds.add_argument("--root", required=True)
    dr = dailies_sub.add_parser("record")
    dr.add_argument("--root", required=True)
    dr.add_argument("--shot-id", required=True)
    dr.add_argument("--candidate", required=True)
    dr.add_argument("--status", choices=("select", "alternate", "reject", "reshoot"), required=True)
    dr.add_argument("--reviewer", required=True)
    dr.add_argument("--notes", default="")
    dr.add_argument("--approved-budget", type=int, default=None)
    dr.add_argument("--provider", default="", help="Generation provider recorded with this take")
    dr.add_argument("--model", default="", help="Generation model recorded with this take")
    dr.add_argument(
        "--cost-usd", type=float, default=None, help="Known provider cost; never inferred"
    )
    dr.add_argument("--source-keyframe", default="", help="Approved source still/keyframe path")
    dr.add_argument("--qa-json", default="", help="Objective QA JSON object")
    dr.add_argument("--director-score", type=int, default=None, help="Director score 1-5")
    dr.add_argument("--issue-tag", action="append", default=[], help="Repeatable quality issue tag")
    dr.add_argument("--reshoot-decision", choices=("none", "reshoot", "repair"), default="")
    dr.add_argument("--selection-rationale", default="")

    canary = sub.add_parser("provider-canary", help="Record or inspect a real provider canary")
    canary_sub = canary.add_subparsers(dest="canary_action", required=True)
    cs = canary_sub.add_parser("status")
    cs.add_argument("--root", required=True)
    cc = canary_sub.add_parser("record")
    cc.add_argument("--root", required=True)
    cc.add_argument("--provider", choices=("grok", "seedance"), required=True)
    cc.add_argument("--output", required=True)
    cc.add_argument("--reviewer", required=True)
    cc.add_argument("--identity-ok", action="store_true")
    cc.add_argument("--motion-ok", action="store_true")
    cc.add_argument("--notes", default="")

    package = sub.add_parser(
        "delivery-package", help="Validate dual-master premium delivery assets"
    )
    package.add_argument("--root", required=True)
    package.add_argument("--allow-missing", action="store_true")

    closure = sub.add_parser(
        "quality-closure", help="No-spend premium benchmark, blind-review, and evidence report"
    )
    closure_sub = closure.add_subparsers(dest="quality_closure_action", required=True)
    closure_package = closure_sub.add_parser("package", help="Write the fixed benchmark package")
    closure_package.add_argument("--root", required=True)
    closure_report = closure_sub.add_parser(
        "report", help="Summarize evidence without inflating claims"
    )
    closure_report.add_argument("--root", required=True)
    closure_review = closure_sub.add_parser("review", help="Record one independent blind review")
    closure_review.add_argument("--root", required=True)
    closure_review.add_argument("--reviewer", required=True)
    closure_review.add_argument("--scores-json", required=True)
    closure_review.add_argument("--notes", default="")

    quality_status = sub.add_parser(
        "quality-status", help="Show hash-bound per-shot quality, motion, and review evidence"
    )
    quality_status.add_argument("--root", required=True)
    quality_status.add_argument("--shot-id")

    qcheck = sub.add_parser(
        "quality-check",
        help="Run 8-gate FFmpeg delivery quality check with weighted scoring",
    )
    qcheck.add_argument("video", help="Final video path")
    qcheck.add_argument("--root", default=None, help="Film root (defaults --out to <root>/out)")
    qcheck.add_argument(
        "--out", default=None, help="Output dir for quality-report.json + artefacts"
    )
    qcheck.add_argument(
        "--expect-audio", action="store_true", default=True, help="Require audio stream"
    )
    qcheck.add_argument("--no-expect-audio", dest="expect_audio", action="store_false")
    qcheck.add_argument("--expect-subtitles", action="store_true", help="Require sidecar SRT")
    qcheck.add_argument("--srt", default=None, help="Expected sidecar SRT file")
    qcheck.add_argument(
        "--min-score", type=int, default=80, help="Minimum score to pass (default 80)"
    )
    qcheck.add_argument(
        "--allow-black", action="store_true", help="Downgrade black-frame fail to warn"
    )
    qcheck.add_argument("--allow-freeze", action="store_true", help="Downgrade freeze fail to warn")

def cmd_heat(args: argparse.Namespace) -> int:
    """Adult heat gates: check | vo-suggest | boost | soften-log | soften-compensate."""
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

    root = Path(str(args.root)).expanduser().resolve()
    action = str(getattr(args, "heat_action", None) or "check")
    try:
        from heat_check import (
            heat_boost,
            heat_check,
            heat_soften_compensate,
            heat_vo_suggest,
        )
    except Exception as exc:  # noqa: BLE001
        raise FilmError(f"Cannot import heat_check: {exc}") from exc
    if action in {"check", ""}:
        report = heat_check(root)
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "vo-suggest":
        report = heat_vo_suggest(root, shot_id=getattr(args, "shot", None))
        emit(report)
        return 0
    if action == "boost":
        report = heat_boost(
            root,
            apply=bool(getattr(args, "apply", False)),
            target_score=float(getattr(args, "target_score", 90.0) or 90.0),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action in {"soften-log", "soften-compensate"}:
        note = str(getattr(args, "note", "") or "moderation softed still/I2V")
        # soften-log is receipt-only; soften-compensate needs --apply to mutate film-spec
        apply = action == "soften-compensate" and bool(getattr(args, "apply", False))
        report = heat_soften_compensate(root, note=note, apply=apply)
        emit(report)
        return 0 if report.get("ok") else 1
    raise FilmError(f"unknown heat action: {action}")


def cmd_preflight(args: argparse.Namespace) -> int:
    """Lesson-based hard/soft gate check before bulk or final."""
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

    skill_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from preflight import PreflightError, run_preflight
    except ImportError as exc:
        raise FilmError(f"Cannot import preflight: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    try:
        report = run_preflight(root)
    except PreflightError as exc:
        raise FilmError(str(exc)) from exc
    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True)
    report["cinematic_audit"] = cinematic
    if not cinematic.get("ok"):
        report.setdefault("hard", []).append(
            {
                "code": "CINEMATIC_AUDIT_FAILED",
                "message": ",".join(cinematic.get("blocking_codes") or []),
            }
        )
        report["hard_ok"] = False
    emit(report)
    if not report.get("hard_ok"):
        return 2
    if getattr(args, "strict", False) and not report.get("soft_ok"):
        return 3
    return 0


def cmd_cinematic_audit(args: argparse.Namespace) -> int:
    """Write a current, checksum-bound cinematic coherence audit without spending."""
    from cinematic_audit import write_audit
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

    report = write_audit(Path(args.root), require_authored_contract=True)
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_quality(args: argparse.Namespace) -> int:
    """Read persisted per-shot quality receipts without touching media."""
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
    from quality_gates import summarize_quality

    report = summarize_quality(Path(args.root), shot_id=getattr(args, "shot_id", None))
    if getattr(args, "shot_id", None):
        from take_registry import compare_takes

        manifest = load_manifest(Path(args.root).expanduser().resolve())
        report["take_comparison"] = compare_takes(manifest, str(args.shot_id))
    emit(report)
    return 0 if report["ok"] else 2


def cmd_takes(args: argparse.Namespace) -> int:
    """Take compare / director review (Film Production OS W5)."""
    from core.emit import emit
    from core.film_io import load_manifest, save_manifest
    from take_registry import compare_takes, set_take_review

    root = Path(args.root).expanduser().resolve()
    action = str(getattr(args, "takes_action", "") or "")
    if action == "compare":
        manifest = load_manifest(root)
        report = compare_takes(manifest, str(args.shot_id))
        report["ok"] = True
        report["root"] = str(root)
        emit(report)
        return 0
    if action == "review":
        manifest = load_manifest(root)
        try:
            report = set_take_review(
                manifest,
                str(args.shot_id),
                take_id=getattr(args, "take_id", None),
                performance=getattr(args, "performance", None),
                continuity=getattr(args, "continuity", None),
                camera=getattr(args, "camera", None),
                artifacts=getattr(args, "artifacts", None),
                director_status=getattr(args, "director_status", None),
            )
        except ValueError as exc:
            from util.errors import FilmError

            raise FilmError(str(exc)) from exc
        save_manifest(root, manifest)
        report["root"] = str(root)
        emit(report)
        return 0 if report.get("ok") else 1
    from util.errors import FilmError

    raise FilmError(f"unknown takes action {action!r}")


def cmd_benchmark(args: argparse.Namespace) -> int:
    from benchmark import run_benchmark
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

    report = run_benchmark(getattr(args, "root", None), suite=str(args.suite), mode=str(args.mode))
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_dialogue_benchmark(args: argparse.Namespace) -> int:
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
    from dialogue_benchmark import build_dialogue_benchmark

    report = build_dialogue_benchmark(Path(args.root))
    emit(report)
    return 0 if report.get("status") == "planned" else 2


def cmd_dialogue_benchmark_review(args: argparse.Namespace) -> int:
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
    from dialogue_benchmark import record_benchmark_arm

    try:
        parameters = json.loads(args.parameters_json)
    except json.JSONDecodeError as exc:
        raise FilmError("--parameters-json must be a JSON object") from exc
    if not isinstance(parameters, dict):
        raise FilmError("--parameters-json must be a JSON object")
    report = record_benchmark_arm(
        Path(args.root),
        weapon=args.weapon,
        artifact=Path(args.artifact),
        reviewer=args.reviewer,
        note=args.note,
        parameters=parameters,
    )
    emit(report)
    return 0


def cmd_dialogue_benchmark_approve(args: argparse.Namespace) -> int:
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
    from dialogue_benchmark import approve_benchmark_parameters

    report = approve_benchmark_parameters(
        Path(args.root), reviewer=args.reviewer, rationale=args.rationale
    )
    emit(report)
    return 0


def cmd_dialogue_production_plan(args: argparse.Namespace) -> int:
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
    from dialogue_production_plan import build_dialogue_production_plan

    try:
        report = build_dialogue_production_plan(Path(args.root))
    except ValueError as exc:
        emit({"ok": False, "status": "blocked", "reason": str(exc)})
        return 2
    emit(report)
    return 0


def cmd_dialogue_benchmark_queue(args: argparse.Namespace) -> int:
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
    from dialogue_benchmark_queue import (
        DialogueBenchmarkQueueError,
        claim,
        complete,
        enqueue,
        status,
        submit_comfy,
    )

    try:
        action = str(args.dialogue_benchmark_queue_action)
        if action == "enqueue":
            report = enqueue(Path(args.root))
        elif action == "claim":
            report = claim(Path(args.root))
        elif action == "complete":
            report = complete(Path(args.root), job_id=args.job_id, claim_token=args.claim_token)
        elif action == "submit-comfy":
            report = submit_comfy(
                Path(args.root),
                job_id=args.job_id,
                claim_token=args.claim_token,
                workflow=Path(args.workflow),
                weapon_id=args.weapon_id,
            )
        else:
            report = status(Path(args.root))
    except DialogueBenchmarkQueueError as exc:
        emit({"ok": False, "status": "blocked", "reason": str(exc)})
        return 2
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_creative_pipeline(args: argparse.Namespace) -> int:
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
    from creative_pipeline import (
        build_animatic_gate,
        build_radio_cut,
        preproduction_readiness,
        write_authoring_receipt,
    )

    root = Path(args.root).expanduser().resolve()
    action = str(args.pipeline_action)
    if action == "readiness":
        report = preproduction_readiness(root)
    elif action == "radio-cut":
        if args.write:
            write_authoring_receipt(
                root,
                "radio-cut",
                {
                    "timing_ok": bool(args.timing_ok),
                    "emotion_turns_ok": bool(args.emotion_turns_ok),
                    "shot_count": int(args.shot_count),
                },
            )
        report = build_radio_cut(root)
    elif action == "animatic":
        if args.write:
            write_authoring_receipt(
                root,
                "animatic",
                {
                    "coverage_ok": bool(args.coverage_ok),
                    "pace_ok": bool(args.pace_ok),
                    "performance_ok": bool(args.performance_ok),
                },
            )
        report = build_animatic_gate(root)
    else:
        raise FilmError(f"Unknown creative pipeline action: {action}")
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_dailies(args: argparse.Namespace) -> int:
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
    from dailies import dailies_status, update_dailies

    root = Path(args.root).expanduser().resolve()
    if args.dailies_action == "status":
        report = dailies_status(root)
    else:
        report = update_dailies(
            root,
            shot_id=args.shot_id,
            candidate=args.candidate,
            status=args.status,
            reviewer=args.reviewer,
            notes=args.notes,
            approved_budget=args.approved_budget,
            provider=args.provider,
            model=args.model,
            cost_usd=args.cost_usd,
            source_keyframe=args.source_keyframe,
            qa=json.loads(args.qa_json) if args.qa_json else None,
            director_score=args.director_score,
            issue_tags=args.issue_tag,
            reshoot_decision=args.reshoot_decision,
            selection_rationale=args.selection_rationale,
        )
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_provider_canary(args: argparse.Namespace) -> int:
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
    from provider_canary import canary_status, record_canary

    root = Path(args.root).expanduser().resolve()
    if args.canary_action == "status":
        report = canary_status(root)
    else:
        report = record_canary(
            root,
            provider=args.provider,
            output=args.output,
            reviewer=args.reviewer,
            identity_ok=args.identity_ok,
            motion_ok=args.motion_ok,
            notes=args.notes,
        )
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_delivery_package(args: argparse.Namespace) -> int:
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
    from delivery_package import build_delivery_package

    report = build_delivery_package(Path(args.root), allow_missing=bool(args.allow_missing))
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_quality_closure(args: argparse.Namespace) -> int:
    """Operate the evidence-only premium quality closure; never spends credits."""
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
    from quality_closure import build_benchmark_package, build_quality_report, record_blind_review

    root = Path(args.root).expanduser().resolve()
    action = str(args.quality_closure_action)
    if action == "package":
        report = build_benchmark_package(root)
    elif action == "report":
        report = build_quality_report(root)
    elif action == "review":
        try:
            scores = json.loads(args.scores_json)
        except json.JSONDecodeError as exc:
            raise FilmError("--scores-json must be a JSON object") from exc
        if not isinstance(scores, dict):
            raise FilmError("--scores-json must be a JSON object")
        report = record_blind_review(root, reviewer=args.reviewer, scores=scores, notes=args.notes)
    else:
        raise FilmError(f"Unknown quality closure action: {action}")
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_quality_status(args: argparse.Namespace) -> int:
    """Read the hash-bound quality, motion, and review receipts for one film."""
    from cli_motion import motion_evidence_status
    from cli_quality import quality_contract_status
    from cli_review import review_packet_status
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

    root = Path(args.root).expanduser().resolve()
    payload: dict[str, Any] = {"quality": quality_contract_status(root)}
    shot_id = getattr(args, "shot_id", None)
    if shot_id:
        payload["motion"] = motion_evidence_status(root, str(shot_id))
        payload["review"] = review_packet_status(root, str(shot_id))
    emit(payload)
    return 0

