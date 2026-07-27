"""CLI adapters for receipt-backed optimization observability."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any


class OptimizationCliError(RuntimeError):
    """User-facing optimization CLI error."""


def add_optimization_parsers(subparsers: Any) -> None:
    """Register optimisation commands without coupling parser setup to the CLI facade."""
    metrics_parser = subparsers.add_parser(
        "metrics", help="Emit receipt-backed optimisation metrics"
    )
    metrics_sub = metrics_parser.add_subparsers(dest="metrics_action", required=True)
    metrics_emit = metrics_sub.add_parser(
        "emit", help="Aggregate one film root into receipts/metrics.json"
    )
    metrics_emit.add_argument("--root", required=True)
    metrics_emit.add_argument("--run-id", default="default")
    metrics_status = metrics_sub.add_parser("status", help="Inspect append-only pipeline events")
    metrics_status.add_argument("--root", required=True)
    metrics_human = metrics_sub.add_parser("human-time", help="Record explicit human minutes")
    metrics_human.add_argument("--root", required=True)
    metrics_human.add_argument("--stage", required=True)
    metrics_human.add_argument("--minutes", type=float, required=True)
    metrics_human.add_argument("--actor", required=True)
    metrics_human.add_argument("--note", default="")
    metrics_human.add_argument("--run-id", default="default")

    experiment_parser = subparsers.add_parser(
        "experiment", help="Receipt-backed, single-axis optimisation experiments"
    )
    experiment_sub = experiment_parser.add_subparsers(dest="experiment_action", required=True)
    experiment_init = experiment_sub.add_parser("init")
    experiment_init.add_argument("--root", required=True)
    experiment_init.add_argument("--id", required=True)
    experiment_init.add_argument("--hypothesis", required=True)
    experiment_init.add_argument("--treatment-axis", required=True)
    experiment_init.add_argument(
        "--primary-metric",
        choices=("cost_usd", "wall_sec", "grade_p50", "motion_p10"),
        required=True,
    )
    experiment_init.add_argument("--min-effect", type=float, required=True)
    experiment_init.add_argument("--fixture", action="append", required=True)
    experiment_init.add_argument("--seed", required=True)
    experiment_init.add_argument("--shot-count", type=int, required=True)
    experiment_init.add_argument("--aspect", required=True)
    experiment_init.add_argument("--duration-budget-sec", type=float, required=True)
    experiment_import = experiment_sub.add_parser("import")
    experiment_import.add_argument("--root", required=True)
    experiment_import.add_argument("--id", required=True)
    experiment_import.add_argument("--arm", choices=("baseline", "treatment"), required=True)
    experiment_import.add_argument("--metrics-root", required=True)
    experiment_import.add_argument("--fixture", action="append", required=True)
    experiment_import.add_argument("--seed", required=True)
    experiment_import.add_argument("--shot-count", type=int, required=True)
    experiment_import.add_argument("--aspect", required=True)
    experiment_import.add_argument("--duration-budget-sec", type=float, required=True)
    experiment_run = experiment_sub.add_parser("run")
    experiment_run.add_argument("--root", required=True)
    experiment_run.add_argument("--id", required=True)
    experiment_run.add_argument("--arm", choices=("baseline", "treatment"), required=True)
    experiment_run.add_argument("--authorize-spend", action="store_true")
    experiment_run.add_argument("--max-usd", type=float, default=None)
    experiment_diff = experiment_sub.add_parser("diff")
    experiment_diff.add_argument("--root", required=True)
    experiment_diff.add_argument("--id", required=True)
    experiment_decide = experiment_sub.add_parser("decide")
    experiment_decide.add_argument("--root", required=True)
    experiment_decide.add_argument("--id", required=True)
    experiment_decide.add_argument("--decision", choices=("ship", "reject"), required=True)

    gold_parser = subparsers.add_parser(
        "gold", help="Calibrate early-reject metrics against a reviewed gold set"
    )
    gold_sub = gold_parser.add_subparsers(dest="gold_action", required=True)
    gold_calibrate = gold_sub.add_parser("calibrate")
    gold_calibrate.add_argument("--manifest", required=True)

    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Build a receipt-only static optimisation dashboard"
    )
    dashboard_sub = dashboard_parser.add_subparsers(dest="dashboard_action", required=True)
    dashboard_build = dashboard_sub.add_parser("build")
    dashboard_build.add_argument("--roots-dir", required=True)
    dashboard_build.add_argument("--days", type=int, default=30)
    dashboard_build.add_argument("--out", required=True)


def _call(
    fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any
) -> tuple[dict[str, Any], int]:
    try:
        report = fn(*args, **kwargs)
    except (ValueError, OSError) as exc:
        raise OptimizationCliError(str(exc)) from exc
    return report, 0


def metrics(args: Namespace) -> tuple[dict[str, Any], int]:
    from optimization_metrics import emit_metrics
    from pipeline_events import append_event, load_events

    action = args.metrics_action
    if action == "emit":
        return _call(emit_metrics, args.root, run_id=args.run_id)
    if action == "status":
        events, invalid = load_events(args.root)
        return {
            "ok": not invalid,
            "kind": "pipeline-events-status",
            "event_count": len(events),
            "invalid": invalid,
        }, 0 if not invalid else 2
    event = append_event(
        args.root,
        stage=args.stage,
        phase="human_time",
        human_minutes=args.minutes,
        actor=args.actor,
        note=args.note,
        run_id=args.run_id,
    )
    return {"ok": True, "kind": "human-time", "event": event}, 0


def experiment(args: Namespace) -> tuple[dict[str, Any], int]:
    from optimization_experiments import (
        decide,
        diff_experiment,
        import_arm,
        init_experiment,
        run_request,
    )

    if args.experiment_action == "init":
        return _call(
            init_experiment,
            args.root,
            experiment_id=args.id,
            hypothesis=args.hypothesis,
            treatment_axis=args.treatment_axis,
            primary_metric=args.primary_metric,
            min_effect=args.min_effect,
            fixtures=args.fixture,
            seed=args.seed,
            shot_count=args.shot_count,
            aspect=args.aspect,
            duration_budget_sec=args.duration_budget_sec,
        )
    if args.experiment_action == "import":
        config = {
            "fixtures": args.fixture,
            "seed": args.seed,
            "shot_count": args.shot_count,
            "aspect": args.aspect,
            "duration_budget_sec": args.duration_budget_sec,
        }
        return _call(
            import_arm,
            args.root,
            experiment_id=args.id,
            arm=args.arm,
            metrics_root=args.metrics_root,
            config=config,
        )
    if args.experiment_action == "run":
        return _call(
            run_request,
            args.root,
            experiment_id=args.id,
            arm=args.arm,
            authorize_spend=args.authorize_spend,
            max_usd=args.max_usd,
        )
    if args.experiment_action == "diff":
        return _call(diff_experiment, args.root, experiment_id=args.id)
    return _call(decide, args.root, experiment_id=args.id, decision=args.decision)


def gold(args: Namespace) -> tuple[dict[str, Any], int]:
    from gold_calibration import calibrate

    report, _ = _call(calibrate, args.manifest)
    return report, 0 if report.get("ok") else 2


def dashboard(args: Namespace) -> tuple[dict[str, Any], int]:
    from optimization_dashboard import build

    return _call(build, args.roots_dir, days=args.days, out=args.out)
