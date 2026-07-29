"""Read-first control surface for the private RTX 5090 support node."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, health, public_health_report
from comfy_armory import probe_armory
from comfy_video import ComfyVideoError, inventory, queue_status
from util import utc_now, write_json


def add_node_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser("node", help="Read and safely recover the private 5090 support node")
    actions = parser.add_subparsers(dest="node_action", required=True)
    for action, help_text in (
        ("status", "Read current node readiness; historical verification never counts as live"),
        ("diagnose", "Read fuller node telemetry and safe remediation hints"),
    ):
        command = actions.add_parser(action, help=help_text)
        command.add_argument("--base-url", default=None)
        command.add_argument("--receipt", type=Path, default=None)
    recover = actions.add_parser(
        "recover", help="Recover only an idle ComfyUI node after confirmation"
    )
    recover.add_argument("--base-url", default=None)
    recover.add_argument("--confirm", action="store_true", help="Required before remote recovery")
    recover.add_argument("--receipt", type=Path, default=None)


def _base_url(value: str | None) -> str:
    return str(
        value or os.environ.get("AIFILM_COMFYUI_BASE_URL") or "http://127.0.0.1:18188"
    ).strip()


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, (OSError, TimeoutError, ConnectionError, ComfyVideoError, AudioNodeError)):
        return "connection_or_protocol_failure"
    return "telemetry_unavailable"


def _audio_status() -> dict[str, Any]:
    base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
    token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
    if not base or not token:
        return {"status": "unavailable", "reason": "not_configured"}
    try:
        report = public_health_report(health(base, token), secret_values=(token,))
    except Exception as exc:
        return {"status": "unavailable", "reason": _safe_reason(exc)}
    return {"status": "reachable" if report.get("ok") else "degraded", **report}


def node_status(base_url: str) -> dict[str, Any]:
    """Return a sanitized live snapshot; no network error text crosses this boundary."""
    comfy: dict[str, Any]
    try:
        observed = inventory(base_url)
        armory = probe_armory(base_url)
        queue = observed.get("queue") if isinstance(observed.get("queue"), dict) else {}
        running, pending = int(queue.get("running", 0)), int(queue.get("pending", 0))
        comfy_status = "busy" if running or pending else "reachable"
        if not armory.get("ready_ids"):
            comfy_status = "degraded"
        comfy = {
            "status": comfy_status,
            "system": observed.get("system", {}),
            "devices": observed.get("devices", []),
            "model_counts": observed.get("model_counts", {}),
            "queue": {"running": running, "pending": pending},
            "weapons": {
                "ready_ids": armory.get("ready_ids", []),
                "blocked_count": len(armory.get("blocked", [])),
            },
            "disk": {"status": "unavailable", "reason": "not_reported_by_comfyui"},
        }
    except Exception as exc:
        comfy = {"status": "unavailable", "reason": _safe_reason(exc)}
    audio = _audio_status()
    statuses = {str(comfy["status"]), str(audio["status"])}
    if "unavailable" in statuses and comfy["status"] == "unavailable":
        status = "unavailable"
    elif "busy" in statuses:
        status = "busy"
    elif "degraded" in statuses or "unavailable" in statuses:
        status = "degraded"
    else:
        status = "reachable"
    return {
        "schema_version": 1,
        "kind": "rtx5090-node-status",
        "at": utc_now(),
        "status": status,
        "live_only": True,
        "comfy": comfy,
        "audio": audio,
        "recovery_requires_idle_queue_and_confirm": True,
    }


def _recover(base_url: str) -> dict[str, Any]:
    queue = queue_status(base_url)
    if queue["running"] or queue["pending"]:
        raise ComfyVideoError("recovery blocked while ComfyUI queue is not idle")
    # Existing CLI recovery owns the narrowly allowlisted Windows service path.
    from comfy_recovery import recover_comfy_from_env

    recovery = recover_comfy_from_env(confirm=True)
    return {
        "schema_version": 1,
        "kind": "rtx5090-node-recovery",
        "at": utc_now(),
        "status": "completed" if recovery.get("ok") else "failed",
        "queue_before": {"running": 0, "pending": 0},
        "operation": "allowlisted_comfy_recovery",
        "recovery": recovery,
        "model_sha256": None,
        "workflow_sha256": None,
        "input_sha256": None,
        "output_sha256": None,
    }


def run_node(args: argparse.Namespace, *, emit: Callable[[dict[str, Any]], None]) -> int:
    base_url = _base_url(getattr(args, "base_url", None))
    try:
        if args.node_action == "status":
            report = node_status(base_url)
        elif args.node_action == "diagnose":
            report = node_status(base_url)
            report["kind"] = "rtx5090-node-diagnose"
            report["remediation"] = (
                "Do not recover until status is unavailable/degraded and the ComfyUI queue is idle. "
                "No model download or provider fallback is implied."
            )
        else:
            if not bool(args.confirm):
                raise ComfyVideoError("node recover requires --confirm")
            report = _recover(base_url)
    except Exception as exc:
        report = {
            "schema_version": 1,
            "kind": "rtx5090-node-error",
            "ok": False,
            "error": str(exc) if isinstance(exc, ComfyVideoError) else _safe_reason(exc),
        }
    receipt = getattr(args, "receipt", None)
    if receipt is not None:
        write_json(Path(receipt).expanduser().resolve(), report)
    emit(report)
    return (
        0
        if report.get("ok", report.get("status") in {"reachable", "busy", "degraded", "completed"})
        else 2
    )
