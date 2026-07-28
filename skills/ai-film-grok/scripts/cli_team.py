"""CLI facade for the production-team orchestration contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def add_team_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "team", help="Specialist director roster and evidence-bound model assignments"
    )
    actions = parser.add_subparsers(dest="team_action", required=True)
    snapshot = actions.add_parser(
        "snapshot", help="Probe M1 and private RTX capability evidence without generating media"
    )
    snapshot.add_argument("--out", required=True)
    snapshot.add_argument("--base-url", default=None)
    scaffold = actions.add_parser("scaffold", help="Write a no-execution production-team template")
    scaffold.add_argument("--root", required=True)
    scaffold.add_argument("--capabilities", required=True)
    scaffold.add_argument("--out", default=None)
    validate = actions.add_parser(
        "validate", help="Validate all director assignments against current evidence"
    )
    validate.add_argument("--plan", required=True)
    validate.add_argument("--capabilities", required=True)
    validate.add_argument(
        "--stage",
        choices=(
            "concept_lock",
            "script_lock",
            "department_look_lock",
            "shot_animatic_lock",
            "pilot_approval",
            "bulk",
            "dailies_review",
            "selects_rough_cut",
            "picture_lock",
            "post_locks",
            "master_lock",
        ),
        default=None,
        help="Check only the directors who own the requested professional stage",
    )


def run(args: Any) -> tuple[dict[str, Any], int]:
    from production_team import scaffold_team, snapshot_capabilities, validate_team

    if args.team_action == "snapshot":
        report = snapshot_capabilities(out=Path(args.out), base_url=args.base_url)
    elif args.team_action == "scaffold":
        report = scaffold_team(
            Path(args.root),
            capabilities_path=Path(args.capabilities),
            out=Path(args.out) if args.out else None,
        )
    else:
        report = validate_team(
            Path(args.plan), capabilities_path=Path(args.capabilities), stage=args.stage
        )
    return report, 0 if report.get("ok") else 2
