"""Orchestration CLI cluster — extracted from aifilm_grok (public cmd strings unchanged).

Commands: next | stage | dispatch | advance | autopilot | craft | selects
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from util.errors import FilmError


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def add_orchestrate_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    disp = sub.add_parser(
        "dispatch",
        help="AUTO orchestrate: craft ring + capability + next_cmd (agent primary entry)",
    )
    disp.add_argument("--root", required=True)
    disp.add_argument("--print-cmd-only", action="store_true", help="Only print next shell command")
    disp.add_argument(
        "--print-instruction",
        action="store_true",
        help="Only print agent_instruction checklist",
    )
    disp.add_argument("--no-capability", action="store_true", help="Skip capability probe (faster)")
    disp.add_argument(
        "--refresh-capability",
        action="store_true",
        help="Bypass the ten-minute guidance cache and run a live capability probe",
    )
    disp.add_argument(
        "--format",
        choices=("compact", "full"),
        default=None,
        dest="dispatch_format",
        help="Output compact agent packet (default) or full audit packet",
    )
    disp.add_argument("--full", action="store_true", help="Alias for --format full")
    disp.add_argument("--no-write", action="store_true", help="Do not write receipts/dispatch.json")

    advance_p = sub.add_parser(
        "advance",
        help="Execute only allowlisted local actions; stop at paid, external or human gates",
    )
    advance_p.add_argument("--root", required=True)
    advance_p.add_argument(
        "--max-local",
        type=int,
        default=3,
        help="Maximum local steps, hard-capped at 10",
    )

    autopilot_p = sub.add_parser(
        "autopilot",
        help="Execute bounded local and budget-authorized external steps; stop at every safety gate",
    )
    autopilot_p.add_argument("--root", required=True)
    autopilot_p.add_argument("--max-actions", type=int, default=3)
    autopilot_p.add_argument("--dry-run", action="store_true")

    craft_p = sub.add_parser(
        "craft",
        help="Craft spine status (idea→story→beats→shots→media→selects→rough→verified)",
    )
    craft_p.add_argument("--root", required=True)
    craft_p.add_argument(
        "craft_action",
        nargs="?",
        default="status",
        choices=["status"],
        help="status (default)",
    )

    sel_p = sub.add_parser("selects", help="Selects ring: planned shots vs approved clips")
    sel_p.add_argument("--root", required=True)
    sel_p.add_argument(
        "selects_action",
        nargs="?",
        default="report",
        choices=["report"],
        help="report (default)",
    )
    sel_p.add_argument("--no-write", action="store_true", help="Do not write selects-report.json")

    nxt = sub.add_parser("next", help="Print next recommended production command")
    nxt.add_argument("--root", required=True)
    nxt.add_argument("--all", action="store_true", help="List full next_actions")
    nxt.add_argument(
        "--print-cmd-only",
        action="store_true",
        help="Stdout only the command string (for shell eval)",
    )
    nxt.add_argument(
        "--print-stage",
        action="store_true",
        help="Also print pipeline stage line on stderr (or with --print-cmd-only)",
    )
    nxt.add_argument(
        "--print-stage-only",
        action="store_true",
        help="Stdout only compact stage line (片 2/7 语音·tts-rehearse); still persists sidecar",
    )

    stg = sub.add_parser(
        "stage",
        help="Show current pipeline layer (agent/visual/voice/design/post/…)",
    )
    stg.add_argument("--root", required=True)
    stg.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit full pipeline_stage JSON",
    )
    stg.add_argument(
        "--full",
        action="store_true",
        help="Long label + next_cmd line",
    )
    stg.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write receipts/pipeline_stage.json or HUD sidecar",
    )


def cmd_next(args: argparse.Namespace) -> int:
    """Print the single next recommended production command (lesson routing)."""
    import aifilm_grok as core

    root = Path(args.root).expanduser().resolve()
    manifest = core.load_manifest(root) if (root / core.MANIFEST_NAME).is_file() else {}
    summary = (
        core.recompute_gates(root, manifest) if manifest else {"gates": {}, "open_reshoot_count": 0}
    )
    if manifest:
        core.save_manifest(root, manifest)
    gates = summary.get("gates") or {}
    open_n = int(summary.get("open_reshoot_count") or 0)
    try:
        actions, pipeline, next_cmd, next_id = core._pipeline_bundle(
            root, gates=gates, open_n=open_n, persist=True
        )
    except Exception as exc:
        raise FilmError(f"next_actions failed: {exc}") from exc
    try:
        from workflow_spine import public_flow_phase

        workflow = pipeline.get("workflow") if isinstance(pipeline, dict) else None
        phase = public_flow_phase(workflow) if isinstance(workflow, dict) else None
    except (ImportError, OSError, ValueError):
        phase = None

    print_stage = bool(getattr(args, "print_stage", False))
    print_stage_only = bool(getattr(args, "print_stage_only", False))
    print_cmd_only = bool(getattr(args, "print_cmd_only", False))

    if print_stage_only:
        from next_actions import format_stage_line

        print(format_stage_line(pipeline, compact=True))
        return 0

    if getattr(args, "all", False):
        core.emit(
            {
                "ok": True,
                "root": str(root),
                "phase": phase,
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "next_actions": actions,
                "next_action": pipeline.get("bound_next_action"),
                "state_hash": pipeline.get("state_hash"),
            }
        )
        return 0
    if not actions:
        if print_stage:
            from next_actions import format_stage_line

            print(format_stage_line(pipeline, compact=True), file=sys.stderr)
        core.emit(
            {
                "ok": True,
                "root": str(root),
                "phase": phase,
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "next_cmd": None,
                "message": "no next action",
            }
        )
        return 0
    cmd = next_cmd or actions[0]["cmd"]
    if print_cmd_only and print_stage:
        # shell-friendly: stage on stderr, cmd on stdout
        from next_actions import format_stage_line

        print(format_stage_line(pipeline, compact=True), file=sys.stderr)
        print(cmd)
        return 0
    if print_cmd_only:
        print(cmd)
        return 0
    if print_stage:
        from next_actions import format_stage_line

        # human mode: one-line stage then full JSON (stage also in payload)
        print(format_stage_line(pipeline, compact=False), file=sys.stderr)
    core.emit(
        {
            "ok": True,
            "root": str(root),
            "phase": phase,
            "pipeline_stage": pipeline,
            "stage": pipeline.get("stage"),
            "stage_label": pipeline.get("label_zh"),
            "next_cmd": cmd,
            "why": actions[0].get("why"),
            "id": next_id or actions[0].get("id"),
            "next_actions": actions,
            "next_action": pipeline.get("bound_next_action"),
            "state_hash": pipeline.get("state_hash"),
        }
    )
    return 0



def cmd_stage(args: argparse.Namespace) -> int:
    """Print / refresh current pipeline stage (product spine layer)."""
    import aifilm_grok as core

    root = Path(args.root).expanduser().resolve()
    manifest = core.load_manifest(root) if (root / core.MANIFEST_NAME).is_file() else {}
    summary = (
        core.recompute_gates(root, manifest) if manifest else {"gates": {}, "open_reshoot_count": 0}
    )
    if manifest:
        core.save_manifest(root, manifest)
    gates = summary.get("gates") or {}
    open_n = int(summary.get("open_reshoot_count") or 0)
    try:
        actions, pipeline, next_cmd, next_id = core._pipeline_bundle(
            root, gates=gates, open_n=open_n, persist=not bool(getattr(args, "no_persist", False))
        )
    except Exception as exc:
        raise FilmError(f"stage detect failed: {exc}") from exc
    from next_actions import format_stage_line

    line = format_stage_line(pipeline, compact=not bool(getattr(args, "full", False)))
    if getattr(args, "json", False) or getattr(args, "as_json", False):
        try:
            from workflow_spine import public_flow_phase

            workflow = pipeline.get("workflow") if isinstance(pipeline, dict) else None
            phase = public_flow_phase(workflow) if isinstance(workflow, dict) else None
        except (ImportError, OSError, ValueError):
            phase = None
        core.emit(
            {
                "ok": True,
                "root": str(root),
                "phase": phase,
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "line": line,
                "next_cmd": next_cmd,
                "next_id": next_id,
                "next_actions": actions[:3] if actions else [],
                "next_action": pipeline.get("bound_next_action"),
                "state_hash": pipeline.get("state_hash"),
            }
        )
        return 0
    if getattr(args, "full", False):
        print(line)
        if next_cmd:
            print(f"next: {next_cmd}")
        return 0
    print(line)
    return 0



def cmd_dispatch(args: argparse.Namespace) -> int:
    """Auto-orchestrate: craft + capability + next → single agent packet."""
    import aifilm_grok as core

    root = Path(args.root).expanduser().resolve()
    from dispatch import build_dispatch
    from dispatch_compact import compact_dispatch, record_orchestration_metrics

    gates: dict[str, Any] = {}
    open_n = 0
    if (root / core.MANIFEST_NAME).is_file():
        man = core.load_manifest(root)
        summary = core.recompute_gates(root, man)
        gates = summary.get("gates") or {}
        open_n = int(summary.get("open_reshoot_count") or 0)

    packet = build_dispatch(
        root,
        gates=gates,
        open_reshoot_count=open_n,
        include_capability=not bool(getattr(args, "no_capability", False)),
        write_receipt=not bool(getattr(args, "no_write", False)),
        refresh_capability=bool(getattr(args, "refresh_capability", False)),
    )
    from project_state import build_project_state, persist_project_state

    project_state = build_project_state(
        root,
        gates=gates,
        open_reshoot_count=open_n,
        next_actions=list(packet.get("next_actions") or []),
        next_cmd=packet.get("next_cmd"),
        next_id=packet.get("next_id"),
    )
    packet["project_state"] = project_state
    if not bool(getattr(args, "no_write", False)):
        packet["project_state_receipt"] = str(persist_project_state(root, project_state))

    # A no-write dispatch is a pure projection; regular dispatch updates the
    # film receipt and HUD from the same canonical snapshot.
    if not bool(getattr(args, "no_write", False)):
        try:
            from next_actions import detect_pipeline_stage, persist_pipeline_stage

            pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_n)
            persisted = persist_pipeline_stage(
                root,
                pipeline,
                next_cmd=packet.get("next_cmd"),
                next_id=packet.get("next_id"),
            )
            if persisted.get("errors"):
                packet["hud_sync_error"] = persisted["errors"]
        except Exception as exc:
            packet["hud_sync_error"] = [str(exc)[:300]]

    if bool(getattr(args, "print_cmd_only", False)):
        print(packet.get("next_cmd") or "")
        return 0 if packet.get("next_cmd") else 1
    if bool(getattr(args, "print_instruction", False)):
        print(packet.get("agent_instruction") or "")
        return 0

    configured_format = (
        str(
            getattr(args, "dispatch_format", None)
            or os.environ.get("AIFILM_DISPATCH_FORMAT")
            or "compact"
        )
        .strip()
        .lower()
    )
    if bool(getattr(args, "full", False)):
        configured_format = "full"
    if configured_format not in {"compact", "full"}:
        raise FilmError("dispatch format must be compact or full")
    output = packet if configured_format == "full" else compact_dispatch(packet)
    if configured_format == "compact" and not bool(getattr(args, "no_write", False)):
        record_orchestration_metrics(root, output)
    core.emit(output)
    return 0 if packet.get("ok") else 1



def cmd_advance(args: argparse.Namespace) -> int:
    """Execute a bounded sequence of allowlisted local dispatch actions."""
    import aifilm_grok as core

    root = Path(args.root).expanduser().resolve()
    from advance import AdvanceError, advance_local

    gates: dict[str, Any] = {}
    open_n = 0
    if (root / core.MANIFEST_NAME).is_file():
        man = core.load_manifest(root)
        summary = core.recompute_gates(root, man)
        gates = summary.get("gates") or {}
        open_n = int(summary.get("open_reshoot_count") or 0)
        core.save_manifest(root, man)
    try:
        report = advance_local(
            root,
            gates=gates,
            open_reshoot_count=open_n,
            max_local=int(args.max_local),
        )
    except AdvanceError as exc:
        raise FilmError(str(exc)) from exc
    core.emit(report)
    return 0 if report.get("ok") else 2



def cmd_autopilot(args: argparse.Namespace) -> int:
    """Run one bounded, budget-authorized automation pass for a film."""
    import aifilm_grok as core

    from autopilot import AutopilotError, autopilot_once

    try:
        report = autopilot_once(
            Path(args.root), max_actions=int(args.max_actions), dry_run=bool(args.dry_run)
        )
    except AutopilotError as exc:
        raise FilmError(str(exc)) from exc
    core.emit(report)
    return 0 if report.get("ok") else 2



def cmd_craft(args: argparse.Namespace) -> int:
    """Craft spine status (idea→verified)."""
    import aifilm_grok as core

    root_s = getattr(args, "root", None)
    if not root_s:
        raise FilmError("craft requires --root")
    root = Path(root_s).expanduser().resolve()
    from craft_spine import craft_status_report

    gates: dict[str, Any] = {}
    if (root / core.MANIFEST_NAME).is_file():
        man = core.load_manifest(root)
        summary = core.recompute_gates(root, man)
        gates = summary.get("gates") or {}
    report = craft_status_report(root, gates=gates)
    core.emit(report)
    return 0



def cmd_selects(args: argparse.Namespace) -> int:
    import aifilm_grok as core

    root_s = getattr(args, "root", None)
    if not root_s:
        raise FilmError("selects requires --root")
    root = Path(root_s).expanduser().resolve()
    from selects_report import build_selects_report

    report = build_selects_report(root, write_receipt=not bool(getattr(args, "no_write", False)))
    core.emit(report)
    return 0 if report.get("ok") or report.get("planned") == 0 else 1


