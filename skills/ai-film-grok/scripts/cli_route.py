"""Read-only production route explanation CLI."""

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


def run(args: Any) -> tuple[dict[str, Any], int]:
    from production_router import explain_route

    report = explain_route(
        Path(args.root),
        shot_id=args.shot_id,
        capabilities_path=Path(args.capabilities) if args.capabilities else None,
        quality_tier=args.quality_tier,
        allow_experimental=bool(args.allow_experimental),
        now=args.now,
    )
    return report, 0 if report.get("ok") else 2
