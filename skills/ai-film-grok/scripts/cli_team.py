"""CLI facade for the production-team orchestration contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def add_team_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "team", help="Specialist director roster and evidence-bound model assignments"
    )
    actions = parser.add_subparsers(dest="team_action", required=True)
    scaffold = actions.add_parser("scaffold", help="Write a no-execution production-team template")
    scaffold.add_argument("--root", required=True)
    scaffold.add_argument("--capabilities", required=True)
    scaffold.add_argument("--out", default=None)
    validate = actions.add_parser(
        "validate", help="Validate all director assignments against current evidence"
    )
    validate.add_argument("--plan", required=True)
    validate.add_argument("--capabilities", required=True)


def run(args: Any) -> tuple[dict[str, Any], int]:
    from production_team import scaffold_team, validate_team

    if args.team_action == "scaffold":
        report = scaffold_team(
            Path(args.root),
            capabilities_path=Path(args.capabilities),
            out=Path(args.out) if args.out else None,
        )
    else:
        report = validate_team(Path(args.plan), capabilities_path=Path(args.capabilities))
    return report, 0 if report.get("ok") else 2
