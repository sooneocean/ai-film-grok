"""CLI registration for the offline creative-workshop contract."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from creative_workshop import (
    WorkshopError,
    compile_workshop,
    diagnose_workshop,
    export_workshop,
    intake_workshop,
    validate_workshop,
)


def add_workshop_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "workshop", help="Creative contracts: intake|diagnose|compile|validate|export"
    )
    sub = parser.add_subparsers(dest="workshop_action", required=True)
    intake = sub.add_parser("intake", help="Write revision-bound creative-brief.json")
    intake.add_argument("--root", required=True)
    intake.add_argument("--file", required=True, help="Creative brief JSON input")
    intake.add_argument("--expected-revision", type=int, required=True)
    for action in ("diagnose", "compile"):
        command = sub.add_parser(action)
        command.add_argument("--root", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--root", required=True)
    validate.add_argument("--strict", action="store_true")
    export = sub.add_parser("export")
    export.add_argument("--root", required=True)
    export.add_argument("--target", choices=("grok", "frw-seedance", "generic"), required=True)


def run_workshop(args: Namespace) -> tuple[dict[str, Any], int]:
    root = Path(args.root).expanduser().resolve()
    try:
        if args.workshop_action == "intake":
            payload = json.loads(Path(args.file).expanduser().read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise WorkshopError("creative brief input must be an object")
            return intake_workshop(root, payload, expected_revision=args.expected_revision), 0
        if args.workshop_action == "diagnose":
            return diagnose_workshop(root), 0
        if args.workshop_action == "compile":
            return compile_workshop(root), 0
        if args.workshop_action == "validate":
            report = validate_workshop(root, strict=bool(args.strict))
            return report, 0 if report["ok"] else 1
        if args.workshop_action == "export":
            return export_workshop(root, target=args.target), 0
    except (OSError, ValueError, WorkshopError) as exc:
        raise WorkshopError(str(exc)) from exc
    raise WorkshopError(f"unknown workshop action {args.workshop_action!r}")
