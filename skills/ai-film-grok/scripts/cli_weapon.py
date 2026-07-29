"""Probe, canary-plan, and promotion-evidence commands for local GPU weapons."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from comfy_armory import ComfyArmoryError, load_armory, probe_armory
from comfy_video import ComfyVideoError
from media_qa import MediaQAError, analyze_media
from util import sha256_file, utc_now, write_json


class WeaponControlError(ValueError):
    pass


def add_weapon_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "weapon", help="Control local 5090 weapon evidence without changing defaults"
    )
    actions = parser.add_subparsers(dest="weapon_action", required=True)
    probe = actions.add_parser("probe", help="Live-check registered weapon requirements")
    probe.add_argument("--base-url", default=None)
    probe.add_argument("--receipt", type=Path, default=None)
    canary = actions.add_parser(
        "canary", help="Plan one bounded canary; it does not submit by default"
    )
    canary.add_argument("--weapon-id", required=True)
    canary.add_argument("--base-url", default=None)
    canary.add_argument("--workflow", type=Path, default=None)
    canary.add_argument("--timeout", type=int, default=1200)
    canary.add_argument("--execute", action="store_true")
    canary.add_argument(
        "--complete", action="store_true", help="Bind decoded media and human review"
    )
    canary.add_argument("--confirm", action="store_true")
    canary.add_argument("--submission-receipt", type=Path, default=None)
    canary.add_argument("--media", type=Path, default=None)
    canary.add_argument("--review-receipt", type=Path, default=None)
    canary.add_argument("--receipt", type=Path, default=None)
    promote = actions.add_parser(
        "promote", help="Create a human-approved promotion packet; never changes defaults"
    )
    promote.add_argument("--weapon-id", required=True)
    promote.add_argument("--canary-receipt", type=Path, required=True)
    promote.add_argument("--review-receipt", type=Path, required=True)
    promote.add_argument("--receipt", type=Path, default=None)


def _weapon(weapon_id: str) -> dict[str, Any]:
    armory = load_armory()
    return next(
        (
            item
            for item in [*armory.get("weapons", []), *armory.get("research_weapons", [])]
            if isinstance(item, dict) and item.get("id") == weapon_id
        ),
        {},
    )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WeaponControlError("receipt must be readable JSON") from exc
    if not isinstance(data, dict):
        raise WeaponControlError("receipt must be a JSON object")
    return data


def _approved(review: dict[str, Any], *, weapon_id: str, output_sha256: str) -> bool:
    return (
        review.get("status") == "approved"
        and review.get("human_reviewed") is True
        and review.get("weapon_id") == weapon_id
        and review.get("output_sha256") == output_sha256
    )


def promotion_packet(weapon_id: str, canary_path: Path, review_path: Path) -> dict[str, Any]:
    canary, review = _read_object(canary_path), _read_object(review_path)
    artifact = canary.get("artifact") if isinstance(canary.get("artifact"), dict) else {}
    output_sha256 = artifact.get("output_sha256")
    if (
        canary.get("weapon_id") != weapon_id
        or canary.get("status") != "completed"
        or not isinstance(output_sha256, str)
        or not isinstance(artifact.get("technical_qa"), dict)
        or artifact["technical_qa"].get("ok") is not True
    ):
        raise WeaponControlError("completed canary receipt must bind the requested weapon")
    if not _approved(review, weapon_id=weapon_id, output_sha256=output_sha256):
        raise WeaponControlError("promotion requires approved human review")
    return {
        "schema_version": 1,
        "kind": "local-weapon-promotion",
        "at": utc_now(),
        "weapon_id": weapon_id,
        "status": "promotion_ready",
        "canary_receipt": {"sha256": sha256_file(canary_path.expanduser().resolve())},
        "review_receipt": {"sha256": sha256_file(review_path.expanduser().resolve())},
        "output_sha256": output_sha256,
        "may_change_default_provider": False,
        "registry_mutated": False,
        "next_step": "Apply a separately reviewed registry change if production routing is desired.",
    }


def _canary_plan(weapon_id: str) -> dict[str, Any]:
    weapon = _weapon(weapon_id)
    if not weapon:
        raise WeaponControlError("unknown registered weapon")
    return {
        "schema_version": 1,
        "kind": "local-weapon-canary",
        "at": utc_now(),
        "weapon_id": weapon_id,
        "status": "planned",
        "allowed_stage": "pilot"
        if weapon.get("status") == "experimental"
        else "production_or_pilot",
        "required_evidence": [
            "workflow_sha256",
            "model_sha256",
            "terminal_media_decode",
            "human_review",
        ],
        "may_change_default_provider": False,
    }


def _complete_canary(args: argparse.Namespace) -> dict[str, Any]:
    if not all((args.submission_receipt, args.media, args.review_receipt)):
        raise WeaponControlError(
            "canary completion requires submission receipt, media, and review receipt"
        )
    submitted = _read_object(args.submission_receipt)
    if submitted.get("weapon_id") != args.weapon_id or submitted.get("status") != "submitted":
        raise WeaponControlError("submission receipt must bind the requested submitted canary")
    media = args.media.expanduser().resolve()
    try:
        technical_qa = analyze_media(media, require_audio=False, require_motion=False)
    except MediaQAError as exc:
        raise WeaponControlError("terminal media decode failed") from exc
    if technical_qa.get("ok") is not True:
        raise WeaponControlError("terminal media decode failed")
    output_sha256 = sha256_file(media)
    review = _read_object(args.review_receipt)
    if not _approved(review, weapon_id=args.weapon_id, output_sha256=output_sha256):
        raise WeaponControlError(
            "canary completion requires approved human review bound to media hash"
        )
    return {
        **_canary_plan(args.weapon_id),
        "status": "completed",
        "submission_receipt": {
            "sha256": sha256_file(args.submission_receipt.expanduser().resolve())
        },
        "review_receipt": {"sha256": sha256_file(args.review_receipt.expanduser().resolve())},
        "artifact": {
            "path": str(media),
            "output_sha256": output_sha256,
            "technical_qa": technical_qa,
        },
    }


def run_weapon(args: argparse.Namespace, *, emit: Callable[[dict[str, Any]], None]) -> int:
    try:
        if args.weapon_action == "probe":
            report = probe_armory(args.base_url)
            armory = load_armory()
            report["research"] = [
                {
                    "id": item.get("id"),
                    "status": item.get("status"),
                    "readiness": item.get("readiness"),
                    "allowed_stages": item.get("allowed_stages", []),
                    "latest_canary_receipt_path": item.get("latest_canary_receipt_path"),
                }
                for item in armory.get("research_weapons", [])
                if isinstance(item, dict)
            ]
        elif args.weapon_action == "canary":
            if args.complete and args.execute:
                raise WeaponControlError("canary completion cannot submit generation")
            report = _complete_canary(args) if args.complete else _canary_plan(args.weapon_id)
            if args.execute:
                if not args.confirm or args.workflow is None:
                    raise WeaponControlError("canary execution requires --workflow and --confirm")
                # Reuse the guarded Comfy submit path; generic workflows cannot bypass armory gates.
                from argparse import Namespace

                from cli_comfy import run_comfy

                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    code = run_comfy(
                        Namespace(
                            base_url=args.base_url,
                            comfy_action="run-workflow",
                            workflow=args.workflow,
                            overrides=None,
                            timeout=args.timeout,
                            allow_external_api_nodes=False,
                            weapon_id=args.weapon_id,
                            production_stage="pilot",
                            allow_experimental=True,
                            receipt=None,
                        )
                    )
                if code != 0:
                    raise WeaponControlError(
                        "canary execution failed; inspect its guarded Comfy receipt"
                    )
                try:
                    report["submission"] = json.loads(captured.getvalue())
                except json.JSONDecodeError as exc:
                    raise WeaponControlError(
                        "guarded Comfy submission returned invalid evidence"
                    ) from exc
                report["status"] = "submitted"
                report["next_step"] = (
                    "Download, full-decode, and human-review the returned media before promotion."
                )
        else:
            report = promotion_packet(args.weapon_id, args.canary_receipt, args.review_receipt)
    except (WeaponControlError, ComfyArmoryError, ComfyVideoError) as exc:
        report = {"schema_version": 1, "kind": "local-weapon-error", "ok": False, "error": str(exc)}
    receipt = getattr(args, "receipt", None)
    if receipt is not None:
        write_json(Path(receipt).expanduser().resolve(), report)
    emit(report)
    return (
        0
        if report.get(
            "ok",
            report.get("status") in {"planned", "submitted", "completed", "promotion_ready"},
        )
        else 2
    )
