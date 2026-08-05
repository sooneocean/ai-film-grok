"""CLI shell for the explicit private-LAN ComfyUI control plane."""

from __future__ import annotations

import argparse
import hashlib
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
    submission_capacity,
    submit,
    upload_image,
    wait_for_result,
    workflow_sha256,
)
from security_policy import load_allowed_env
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

    capacity_parser = actions.add_parser(
        "capacity",
        help="Fail-closed RAM, VRAM and queue admission check for a heavy workflow",
    )
    _add_base_url(capacity_parser)
    capacity_parser.add_argument("--receipt", type=Path, default=None)

    recovery_parser = actions.add_parser(
        "recover",
        help="Repair the verified SSH tunnel or restart only the remote ComfyUI service",
    )
    _add_base_url(recovery_parser)
    recovery_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required because a failed remote service may be restarted",
    )
    recovery_parser.add_argument("--receipt", type=Path, default=None)

    armory_parser = actions.add_parser(
        "armory",
        help="List verified local GPU weapons and optionally live-check installed models",
    )
    _add_base_url(armory_parser)
    armory_parser.add_argument(
        "--live",
        action="store_true",
        help="Read current ComfyUI model folders and report only truly ready weapons",
    )
    armory_parser.add_argument("--receipt", type=Path, default=None)

    route_parser = actions.add_parser(
        "route",
        help="Select the highest-priority pilot-verified weapon for an image intent",
    )
    _add_base_url(route_parser)
    route_parser.add_argument("--intent", required=True)
    route_parser.add_argument("--quality", default="max_practical")
    route_parser.add_argument("--identity-lock", action="store_true")
    route_parser.add_argument(
        "--production-stage",
        choices=("pilot", "production"),
        default="production",
    )
    route_parser.add_argument(
        "--allow-experimental",
        action="store_true",
        help="Allow a verified experimental weapon for a pilot; never promotes it",
    )
    route_parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip current model read-back; live verification is the default",
    )
    route_parser.add_argument("--receipt", type=Path, default=None)

    prepare_parser = actions.add_parser(
        "prepare",
        help="Route an intent and compile a local-only API workflow without submitting it",
    )
    _add_base_url(prepare_parser)
    prepare_parser.add_argument("--intent", required=True)
    prepare_parser.add_argument("--quality", default="max_practical")
    prepare_parser.add_argument("--identity-lock", action="store_true")
    prepare_parser.add_argument("--prompt-file", type=Path, required=True)
    prepare_parser.add_argument("--seed", type=int, required=True)
    prepare_parser.add_argument("--input-image-name", default=None)
    prepare_parser.add_argument("--input-audio-name", default=None)
    prepare_parser.add_argument(
        "--steps",
        type=int,
        default=None,
        help="Use only a registered pilot step value for the selected weapon",
    )
    prepare_parser.add_argument("--filename-prefix", default="aifilm/armory")
    prepare_parser.add_argument(
        "--production-stage",
        choices=("pilot", "production"),
        default="production",
    )
    prepare_parser.add_argument(
        "--allow-experimental",
        action="store_true",
        help="Allow a pilot-verified experimental weapon; never promotes it",
    )
    prepare_parser.add_argument("--out", type=Path, required=True)
    prepare_parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip current model and node read-back; live verification is the default",
    )
    prepare_parser.add_argument("--receipt", type=Path, default=None)

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
        "--enqueue",
        action="store_true",
        help="Queue an explicitly authorized pilot behind existing ComfyUI work",
    )
    run_parser.add_argument(
        "--allow-external-api-nodes",
        action="store_true",
        help="Allow workflow nodes that may call paid external providers",
    )
    run_parser.add_argument(
        "--weapon-id",
        default=None,
        help="Validate against one registered armory template, including exact custom-node modules",
    )
    run_parser.add_argument(
        "--production-stage",
        choices=("pilot", "production"),
        default="production",
    )
    run_parser.add_argument(
        "--allow-experimental",
        action="store_true",
        help="Required with an experimental --weapon-id; pilot-only",
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
        from comfy_armory import ComfyArmoryError, default_base_url

        try:
            value = default_base_url()
        except ComfyArmoryError as exc:
            raise ComfyVideoError(
                "ComfyUI URL is required via --base-url, AIFILM_COMFYUI_BASE_URL, "
                "or a verified armory default"
            ) from exc
    return value


def _maybe_write_receipt(args: argparse.Namespace, report: dict[str, Any]) -> None:
    receipt = getattr(args, "receipt", None)
    if receipt is not None:
        write_json(Path(receipt).expanduser().resolve(), report)


def run_comfy(args: argparse.Namespace) -> int:
    load_allowed_env(
        Path(__file__).resolve().parents[2] / "config.env",
        allowed_keys={
            "AIFILM_COMFY_DRIVER_VRAM_FALLBACK",
            "AIFILM_COMFY_SSH_TARGET",
            "AIFILM_COMFY_SSH_KEY",
            "AIFILM_COMFY_SSH_KNOWN_HOSTS",
            "AIFILM_COMFY_SSH_HOSTKEY_ALIAS",
            "AIFILM_COMFY_SSH_EXPECTED_HOSTNAME",
        },
    )
    try:
        base_url = _base_url(args)
        action = args.comfy_action
        if action == "probe":
            report = probe(base_url)
        elif action == "inventory":
            report = inventory(base_url)
        elif action == "capacity":
            report = submission_capacity(base_url)
        elif action == "recover":
            from comfy_recovery import ComfyRecoveryError, recover_comfy_from_env

            try:
                report = recover_comfy_from_env(confirm=bool(args.confirm))
            except ComfyRecoveryError as exc:
                raise ComfyVideoError(str(exc)) from exc
        elif action == "armory":
            from comfy_armory import load_armory, probe_armory

            report = probe_armory(base_url) if args.live else load_armory()
        elif action in {"route", "prepare"}:
            from comfy_armory import (
                ComfyArmoryError,
                compile_weapon_workflow,
                probe_armory,
                select_weapon,
            )

            try:
                live = None if args.offline else probe_armory(base_url)
                route = select_weapon(
                    args.intent,
                    quality=args.quality,
                    identity_lock=bool(args.identity_lock),
                    ready_ids=set(live["ready_ids"]) if live is not None else None,
                    stage=str(getattr(args, "production_stage", "production")),
                    allow_experimental=bool(getattr(args, "allow_experimental", False)),
                )
                if action == "route":
                    report = route
                    if live is not None:
                        report["live_model_readback"] = True
                else:
                    try:
                        prompt = (
                            args.prompt_file.expanduser()
                            .resolve()
                            .read_text(encoding="utf-8")
                            .strip()
                        )
                    except OSError as exc:
                        raise ComfyArmoryError(f"cannot read prompt file: {exc}") from exc
                    graph = compile_weapon_workflow(
                        route["weapon"]["id"],
                        prompt=prompt,
                        seed=args.seed,
                        input_image_name=args.input_image_name,
                        input_audio_name=args.input_audio_name,
                        filename_prefix=args.filename_prefix,
                        steps=args.steps,
                    )
                    if not args.offline:
                        from comfy_armory import assert_registered_weapon_workflow

                        assert_registered_weapon_workflow(
                            base_url,
                            route["weapon"]["id"],
                            graph,
                        )
                    output = args.out.expanduser().resolve()
                    write_json(output, graph)
                    report = {
                        "schema_version": 1,
                        "kind": "comfy-weapon-preparation",
                        "ok": True,
                        "weapon_id": route["weapon"]["id"],
                        "intent": route["intent"],
                        "quality": route["quality"],
                        "workflow": str(output),
                        "workflow_sha256": workflow_sha256(graph),
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "live_model_readback": not bool(args.offline),
                        "external_api_nodes_allowed": False,
                        "source_endpoint": route["weapon"].get("source_endpoint"),
                        "pilot_only": bool(
                            (route["weapon"].get("capabilities") or {}).get("pilot_only")
                        ),
                    }
            except ComfyArmoryError as exc:
                raise ComfyVideoError(str(exc)) from exc
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
            registered_weapon = None
            effective_weapon_id = args.weapon_id
            if not effective_weapon_id:
                from comfy_armory import (
                    ComfyArmoryError,
                    identify_registered_weapon_workflow,
                )

                try:
                    identified = identify_registered_weapon_workflow(graph)
                except ComfyArmoryError as exc:
                    raise ComfyVideoError(str(exc)) from exc
                if identified is not None:
                    effective_weapon_id = str(identified["id"])
            if effective_weapon_id:
                if args.allow_external_api_nodes:
                    raise ComfyVideoError(
                        "--weapon-id cannot be combined with --allow-external-api-nodes"
                    )
                from comfy_armory import (
                    ComfyArmoryError,
                    assert_registered_weapon_workflow,
                    authorize_weapon_execution,
                )

                try:
                    registered_weapon = authorize_weapon_execution(
                        effective_weapon_id,
                        stage=args.production_stage,
                        allow_experimental=bool(args.allow_experimental),
                    )
                    assert_registered_weapon_workflow(
                        base_url,
                        effective_weapon_id,
                        graph,
                    )
                except ComfyArmoryError as exc:
                    raise ComfyVideoError(str(exc)) from exc
            if args.enqueue and (registered_weapon is None or args.production_stage != "pilot"):
                raise ComfyVideoError("--enqueue requires a registered pilot weapon")
            elif registered_weapon is None and not args.allow_external_api_nodes:
                assert_local_only_workflow(base_url, graph)
            client_id = f"aifilm-{secrets.token_hex(8)}"
            prompt_id = submit(
                base_url,
                graph,
                client_id=client_id,
                weapon_id=effective_weapon_id,
                allow_queue=bool(args.enqueue),
            )
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
                "weapon_id": effective_weapon_id,
                "source_endpoint": (
                    registered_weapon.get("source_endpoint") if registered_weapon else None
                ),
                "pilot_only": bool(
                    ((registered_weapon or {}).get("capabilities") or {}).get("pilot_only")
                ),
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
