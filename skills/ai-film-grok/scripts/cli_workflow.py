"""CLI shell for Wave A–C throughput commands (closeout / pilot pack / preflight / lease)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from workflow_pack import (
    WorkflowPackError,
    bulk_preflight,
    gpu_lease_acquire,
    gpu_lease_heartbeat,
    gpu_lease_release,
    gpu_lease_status,
    queue_progress_honest,
    select_shortlist,
    tunnel_probe,
    variety_precheck,
)


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def add_workflow_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # closeout status|run lives on aifilm_grok (closeout.py) — do not re-register.
    # Preferred pilot GO: `aifilm pilot pack`. Keep hyphen alias for agents.
    pack = sub.add_parser(
        "pilot-pack",
        help="Alias of `pilot pack` — GO pack → receipts/pilot-go.json",
    )
    pack.add_argument("--root", required=True)
    pack.add_argument("--shots", default="", help="Comma shot ids (default auto-pick)")

    # bulk-preflight
    bp = sub.add_parser(
        "bulk-preflight",
        help="Single-door bulk readiness (pilot/heat/state/still/anatomy/tunnel/lease)",
    )
    bp.add_argument("--root", required=True)
    bp.add_argument("--no-tunnel", action="store_true")
    bp.add_argument("--tunnel-port", type=int, default=18188)
    bp.add_argument("--no-lease", action="store_true")

    # variety
    vp = sub.add_parser(
        "variety-precheck",
        help="Design-time anti-boring matrix (poses / face CU / adjacent motion)",
    )
    vp.add_argument("--root", required=True)

    # select shortlist
    ss = sub.add_parser(
        "select-shortlist",
        help="Multi-take preferred shortlist (advisory; never deletes takes)",
    )
    ss.add_argument("--root", required=True)

    # gpu-lease
    gl = sub.add_parser("gpu-lease", help="5090 one-owner lease (global ~/.grok/run)")
    gl_sub = gl.add_subparsers(dest="lease_action", required=True)
    for action, help_text in (
        ("status", "Show lease free/owner"),
        ("acquire", "Acquire lease for this film root"),
        ("heartbeat", "Refresh heartbeat"),
        ("release", "Release if owned by this root"),
    ):
        p = gl_sub.add_parser(action, help=help_text)
        p.add_argument("--root", required=True)
        if action in {"acquire", "release"}:
            p.add_argument("--force", action="store_true")

    # tunnel-probe
    tp = sub.add_parser(
        "tunnel-probe",
        help="Probe localhost Comfy tunnel (18188→8188 system_stats)",
    )
    tp.add_argument("--port", type=int, default=18188)
    tp.add_argument("--timeout", type=float, default=3.0)

    # queue progress
    qp = sub.add_parser(
        "queue-progress",
        help="Honest progress: non-empty takes/clips file counts only",
    )
    qp.add_argument("--root", required=True)


def run_workflow_cmd(args: argparse.Namespace) -> int:
    """Dispatch workflow-related top-level cmds. Returns process exit code."""
    cmd = str(getattr(args, "cmd", "") or "")
    try:
        if cmd == "pilot-pack":
            from pilot_pack import pilot_pack

            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            report = pilot_pack(args.root, shots=shots)
            _emit(report)
            return 0 if report.get("ok") or report.get("go_ready") else 2

        if cmd == "bulk-preflight":
            report = bulk_preflight(
                args.root,
                probe_tunnel=not bool(getattr(args, "no_tunnel", False)),
                tunnel_port=int(getattr(args, "tunnel_port", 18188) or 18188),
                check_lease=not bool(getattr(args, "no_lease", False)),
            )
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "variety-precheck":
            report = variety_precheck(args.root)
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "select-shortlist":
            report = select_shortlist(args.root)
            _emit(report)
            return 0

        if cmd == "gpu-lease":
            action = str(getattr(args, "lease_action", "") or "")
            root = args.root
            force = bool(getattr(args, "force", False))
            if action == "status":
                report = gpu_lease_status(root)
            elif action == "acquire":
                report = gpu_lease_acquire(root, force=force)
            elif action == "heartbeat":
                report = gpu_lease_heartbeat(root)
            elif action == "release":
                report = gpu_lease_release(root, force=force)
            else:
                raise WorkflowPackError(f"unknown lease action: {action}")
            _emit(report)
            return 0 if report.get("ok") is not False else 2

        if cmd == "tunnel-probe":
            report = tunnel_probe(
                port=int(getattr(args, "port", 18188) or 18188),
                timeout=float(getattr(args, "timeout", 3.0) or 3.0),
            )
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "queue-progress":
            report = queue_progress_honest(args.root)
            _emit(report)
            return 0

    except WorkflowPackError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1

    print(f"unknown workflow cmd: {cmd}", file=sys.stderr)
    return 2


# Compatibility: allow `python cli_workflow.py` smoke (not the main entry)
if __name__ == "__main__":
    print("use: aifilm pilot-pack|bulk-preflight|variety-precheck|gpu-lease|…", file=sys.stderr)
    sys.exit(2)
