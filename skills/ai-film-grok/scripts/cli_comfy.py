"""CLI shell for the explicit private-LAN ComfyUI control plane."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path
from typing import Any

from comfy_video import (
    ComfyVideoError,
    apply_workflow_overrides,
    assert_local_only_workflow,
    cancel_prompt,
    download_result,
    free_memory,
    inventory,
    load_api_workflow,
    probe,
    queue_status,
    submit,
    upload_image,
    wait_for_result,
    workflow_sha256,
)
from util import write_json


def _add_base_url(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=None,
        help="Private ComfyUI URL; defaults to AIFILM_COMFYUI_BASE_URL",
    )


def add_comfy_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "comfy",
        help="Control an explicit private-LAN ComfyUI node",
    )
    actions = parser.add_subparsers(dest="comfy_action", required=True)

    probe_parser = actions.add_parser("probe", help="Check RTX/Wan capability")
    _add_base_url(probe_parser)
    probe_parser.add_argument("--receipt", type=Path, default=None)

    inventory_parser = actions.add_parser(
        "inventory",
        help="Read bounded system, queue, feature and model counts",
    )
    _add_base_url(inventory_parser)
    inventory_parser.add_argument("--receipt", type=Path, default=None)

    queue_parser = actions.add_parser("queue", help="Show prompt IDs without prompt payloads")
    _add_base_url(queue_parser)

    upload_parser = actions.add_parser("upload", help="Upload one local input without overwrite")
    _add_base_url(upload_parser)
    upload_parser.add_argument("--file", type=Path, required=True)

    run_parser = actions.add_parser(
        "run-workflow",
        help="Submit a ComfyUI API-format workflow and wait for outputs",
    )
    _add_base_url(run_parser)
    run_parser.add_argument("--workflow", type=Path, required=True)
    run_parser.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help='JSON object such as {"6":{"text":"prompt"},"3":{"seed":42}}',
    )
    run_parser.add_argument("--timeout", type=int, default=1200)
    run_parser.add_argument(
        "--allow-external-api-nodes",
        action="store_true",
        help="Allow workflow nodes that may call paid external providers",
    )
    run_parser.add_argument("--receipt", type=Path, default=None)

    download_parser = actions.add_parser("download", help="Download one named output")
    _add_base_url(download_parser)
    download_parser.add_argument("--filename", required=True)
    download_parser.add_argument("--subfolder", default="")
    download_parser.add_argument("--type", choices=("input", "output", "temp"), default="output")
    download_parser.add_argument("--out", type=Path, required=True)

    cancel_parser = actions.add_parser("cancel", help="Cancel only the named active prompt")
    _add_base_url(cancel_parser)
    cancel_parser.add_argument("--prompt-id", required=True)
    cancel_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required because this mutates the remote queue",
    )

    free_parser = actions.add_parser("free-memory", help="Unload models and free ComfyUI memory")
    _add_base_url(free_parser)
    free_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required because this mutates remote model state",
    )


def _base_url(args: argparse.Namespace) -> str:
    value = str(args.base_url or os.environ.get("AIFILM_COMFYUI_BASE_URL") or "").strip()
    if not value:
        raise ComfyVideoError("ComfyUI URL is required via --base-url or AIFILM_COMFYUI_BASE_URL")
    return value


def _maybe_write_receipt(args: argparse.Namespace, report: dict[str, Any]) -> None:
    receipt = getattr(args, "receipt", None)
    if receipt is not None:
        write_json(Path(receipt).expanduser().resolve(), report)


def run_comfy(args: argparse.Namespace) -> int:
    try:
        base_url = _base_url(args)
        action = args.comfy_action
        if action == "probe":
            report = probe(base_url)
        elif action == "inventory":
            report = inventory(base_url)
        elif action == "queue":
            report = {"ok": True, "kind": "comfy-lan-queue", **queue_status(base_url)}
        elif action == "upload":
            report = {
                "ok": True,
                "kind": "comfy-lan-upload",
                "remote": upload_image(base_url, args.file),
            }
        elif action == "run-workflow":
            graph = load_api_workflow(args.workflow)
            if args.overrides is not None:
                try:
                    overrides = json.loads(
                        args.overrides.expanduser().resolve().read_text(encoding="utf-8")
                    )
                except (OSError, ValueError) as exc:
                    raise ComfyVideoError(f"cannot read workflow overrides: {exc}") from exc
                if not isinstance(overrides, dict):
                    raise ComfyVideoError("workflow overrides must be a JSON object")
                graph = apply_workflow_overrides(graph, overrides)
            if not args.allow_external_api_nodes:
                assert_local_only_workflow(base_url, graph)
            client_id = f"aifilm-{secrets.token_hex(8)}"
            prompt_id = submit(base_url, graph, client_id=client_id)
            result = wait_for_result(
                base_url,
                prompt_id,
                client_id=client_id,
                timeout_sec=args.timeout,
            )
            report = {
                "schema_version": 1,
                "kind": "comfy-lan-workflow",
                "ok": True,
                "prompt_id": prompt_id,
                "workflow_sha256": workflow_sha256(graph),
                "artifacts": result.get("artifacts") or [],
                "external_api_nodes_allowed": bool(args.allow_external_api_nodes),
            }
        elif action == "download":
            report = {
                "ok": True,
                "kind": "comfy-lan-download",
                **download_result(
                    base_url,
                    {
                        "filename": args.filename,
                        "subfolder": args.subfolder,
                        "type": args.type,
                    },
                    args.out,
                ),
            }
        elif action == "cancel":
            if not args.confirm:
                raise ComfyVideoError("cancel requires --confirm")
            report = cancel_prompt(base_url, args.prompt_id)
        elif action == "free-memory":
            if not args.confirm:
                raise ComfyVideoError("free-memory requires --confirm")
            report = free_memory(base_url)
        else:  # pragma: no cover - argparse enforces choices
            raise ComfyVideoError(f"unsupported comfy action: {action}")
        _maybe_write_receipt(args, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 2
    except ComfyVideoError as exc:
        print(
            json.dumps(
                {"ok": False, "kind": "comfy-lan-error", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
