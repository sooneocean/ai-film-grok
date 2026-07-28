"""Production route explanation and non-authorized planning CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def add_route_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "route",
        help="Explain deterministic shot routing from an evidence-bearing capability snapshot",
    )
    actions = parser.add_subparsers(dest="route_action", required=True)
    explain = actions.add_parser(
        "explain",
        help="Explain one shot route without probing, writing, submitting, or spending",
    )
    explain.add_argument("--root", required=True)
    explain.add_argument("--shot-id", required=True)
    explain.add_argument("--capabilities", default=None)
    explain.add_argument(
        "--quality-tier",
        choices=("draft", "select", "hero"),
        default="draft",
    )
    explain.add_argument("--allow-experimental", action="store_true")
    explain.add_argument(
        "--now", default=None, help="ISO-8601 evaluation time for reproducible audits"
    )
    explain.set_defaults(no_write=True)
    plan = actions.add_parser(
        "plan",
        help="Preview a hash-bound execution plan; --write only records planned local receipts",
    )
    plan.add_argument("--root", required=True)
    plan.add_argument("--shot-id", required=True)
    plan.add_argument("--capabilities", default=None)
    plan.add_argument(
        "--quality-tier",
        choices=("draft", "select", "hero"),
        default="draft",
    )
    plan.add_argument("--allow-experimental", action="store_true")
    plan.add_argument(
        "--now", default=None, help="ISO-8601 evaluation time for reproducible audits"
    )
    plan.add_argument(
        "--write",
        action="store_true",
        help="Write local planned receipts only; never authorizes or submits a provider request",
    )


def _routing_kwargs(args: Any) -> dict[str, Any]:
    return {
        "shot_id": args.shot_id,
        "capabilities_path": Path(args.capabilities) if args.capabilities else None,
        "quality_tier": args.quality_tier,
        "allow_experimental": bool(args.allow_experimental),
        "now": args.now,
    }


def run(args: Any) -> tuple[dict[str, Any], int]:
    from production_router import explain_route, plan_route

    root = Path(args.root)
    if args.route_action == "plan":
        report = plan_route(root, write=bool(args.write), **_routing_kwargs(args))
    else:
        report = explain_route(root, **_routing_kwargs(args))
    return report, 0 if report.get("ok") else 2
