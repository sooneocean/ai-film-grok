"""Skill Registry CLI route, kept independent from the media control plane."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from skill_registry import list_skills, show_skill, validate_skill_payload
from util import read_json


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    action = str(getattr(args, "skill_action", "") or "")
    if action == "list":
        report = list_skills(tag=getattr(args, "tag", None), phase=getattr(args, "phase", None))
    elif action == "show":
        sid = getattr(args, "id", None) or getattr(args, "skill_id", None)
        if not sid:
            return {"ok": False, "error": "skill show requires --id"}, 1
        report = show_skill(str(sid))
    elif action == "validate":
        payload = read_json(Path(args.payload_file).expanduser())
        report = validate_skill_payload(str(args.skill_id), payload, direction=str(args.direction))
    else:
        return {"ok": False, "error": f"unknown skill action {action!r}"}, 1
    return report, 0 if report.get("ok") else 1
