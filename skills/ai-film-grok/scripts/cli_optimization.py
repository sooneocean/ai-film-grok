"""CLI adapters for receipt-backed optimization observability."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any


class OptimizationCliError(RuntimeError):
    """User-facing optimization CLI error."""


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
