"""Review/visual-text CLI — extracted from aifilm_grok (public cmd strings unchanged).

Uses scripts/core for film IO/emit/gates (no hub cycle for basic IO).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from media_qa import MediaQAError
from util.errors import FilmError


def add_review_ops_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    shot_review = sub.add_parser(
        "review-shot",
        help="Create evidence-backed first/middle/last-frame director review for one clip",
    )
    shot_review.add_argument("--root", required=True)
    shot_review.add_argument("--shot-id", required=True)
    shot_review.add_argument("--source", required=True)
    shot_review.add_argument(
        "--approve",
        action="store_true",
        help="Approve only if QA, 1–5 scores, and timestamp evidence all pass",
    )
    shot_review.add_argument("--reviewer", required=True)
    shot_review.add_argument("--notes", required=True)
    for dim in ("identity", "continuity", "composition", "motion", "narrative"):
        shot_review.add_argument(
            f"--score-{dim}", type=int, choices=range(1, 6), required=True, dest=f"score_{dim}"
        )
    shot_review.add_argument(
        "--score-coitus",
        type=int,
        choices=range(1, 6),
        required=False,
        default=None,
        dest="score_coitus",
        help="Optional mute-frame intercourse readability 1-5 (adult max)",
    )
    shot_review.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Repeat dimension@seconds:note for every review dimension",
    )
    shot_review.add_argument(
        "--performance-evidence",
        action="append",
        default=[],
        help=(
            "Repeat kind@seconds:note. Required authored story facts use "
            "start_state_visible, must_show_visible, visible_change_visible, end_state_visible; "
            "also action_visible, trigger_visible, reaction_visible, dialogue_delivery, mouth_still"
        ),
    )
    shot_review.add_argument(
        "--reference", action="append", default=[], help="Optional reference asset path; repeatable"
    )

    review_pack = sub.add_parser(
        "review-pack",
        help="Create an unapproved local decode, frame, contact-sheet and hash evidence package",
    )
    review_pack.add_argument("--root", required=True)
    review_pack.add_argument("--id", required=True, help="Stable review package id")
    review_pack.add_argument("--source", help="Existing local video path")
    review_pack.add_argument(
        "--comfy-filename",
        help="Download this named Comfy output first; mutually exclusive with --source",
    )
    review_pack.add_argument("--comfy-base-url", help="ComfyUI base URL for --comfy-filename")
    review_pack.add_argument("--comfy-subfolder", default="")
    review_pack.add_argument("--comfy-type", choices=("input", "output", "temp"), default="output")
    review_pack.add_argument("--no-expect-audio", dest="expect_audio", action="store_false")
    review_pack.set_defaults(expect_audio=True)

    review_contract = sub.add_parser(
        "review-contract",
        help="Explicitly migrate a legacy film root to v1.6 review evidence gates",
    )
    review_contract_sub = review_contract.add_subparsers(
        dest="review_contract_action", required=True
    )
    review_contract_migrate = review_contract_sub.add_parser(
        "migrate", help="Require real shot reviews for historical approved clips"
    )
    review_contract_migrate.add_argument("--root", required=True)
    review_contract_v3 = review_contract_sub.add_parser(
        "upgrade-v3", help="Opt into grades and canonical fail reasons for future final reviews"
    )
    review_contract_v3.add_argument("--root", required=True)

    external_review = sub.add_parser(
        "external-review",
        help="Read-only Groq/Gemini candidate review; never changes production gates",
    )
    external_review_sub = external_review.add_subparsers(
        dest="external_review_action", required=True
    )
    external_review_sub.add_parser(
        "probe", help="Check local credential presence only; sends no media or inference request"
    )
    external_run = external_review_sub.add_parser(
        "run", help="Write a hash-bound candidate-only external review report"
    )
    external_run.add_argument("--root", required=True, help="Film workspace root")
    external_run.add_argument(
        "--video", required=True, help="Verified local MP4/audio source in root"
    )
    external_run.add_argument("--subtitles", default=None, help="Optional in-root SRT sidecar")
    external_run.add_argument(
        "--director-contract", default=None, help="Optional in-root contract JSON"
    )
    external_run.add_argument(
        "--sanitized-frame-index",
        default=None,
        help="Optional in-root JSON list of declared safe frame paths; max five frames",
    )
    external_run.add_argument(
        "--sanitized",
        action="store_true",
        help="Required for adult technical samples and every external frame upload",
    )
    external_run.add_argument(
        "--purpose",
        choices=("tts_rehearsal", "animatic", "final"),
        default="final",
        help="Audit stage recorded in the candidate-only receipt; default final",
    )

    local_omni = sub.add_parser(
        "local-omni-review",
        help="Opt-in private frame review; candidate-only and cannot approve production",
    )
    local_omni_sub = local_omni.add_subparsers(dest="local_omni_review_action", required=True)
    local_omni_probe = local_omni_sub.add_parser(
        "probe", help="Read the private model list without sending frames or starting inference"
    )
    local_omni_run = local_omni_sub.add_parser(
        "run", help="Review declared sanitized workspace frames and write a candidate-only report"
    )
    for action_parser in (local_omni_probe, local_omni_run):
        action_parser.add_argument(
            "--base-url",
            default=os.environ.get("AIFILM_LOCAL_OMNI_BASE_URL", ""),
            help="Private OpenAI-compatible /v1 URL (or AIFILM_LOCAL_OMNI_BASE_URL)",
        )
        action_parser.add_argument(
            "--model",
            default="nvidia/nemotron-nano-3-30b-a3b",
            help="Private multimodal model id; default NVIDIA Nemotron Nano 30B A3B",
        )
    local_omni_run.add_argument("--root", required=True, help="Film workspace root")
    local_omni_run.add_argument(
        "--frame-index",
        required=True,
        help="In-root JSON list of 1-5 declared sanitized technical frames",
    )
    local_omni_run.add_argument(
        "--sanitized",
        action="store_true",
        help="Required declaration: frames are safe technical review samples",
    )
    local_omni_run.add_argument("--timeout", type=int, default=60, help="1-120 seconds; default 60")

    visual_text_audit = sub.add_parser(
        "visual-text-audit",
        help="Fail-closed every-frame inspection for provider-burned visual text",
    )
    visual_text_audit.add_argument("--root", required=True)
    visual_text_audit.add_argument(
        "--source", required=True, help="Video inside the film workspace"
    )
    visual_text_audit.add_argument(
        "--base-url", default=os.environ.get("AIFILM_LOCAL_OMNI_BASE_URL", "")
    )
    visual_text_audit.add_argument("--model", default="nvidia/nemotron-nano-3-30b-a3b")

    visual_text_repair = sub.add_parser(
        "visual-text-repair",
        help="Repair a rejected visual-text audit with bounded Qwen I2I frame edits",
    )
    visual_text_repair.add_argument("--root", required=True)
    visual_text_repair.add_argument(
        "--source", required=True, help="Rejected video inside the film workspace"
    )
    visual_text_repair.add_argument(
        "--base-url", default=os.environ.get("AIFILM_COMFYUI_BASE_URL", "http://127.0.0.1:18188")
    )
    visual_text_repair.add_argument("--audit-receipt", default=None)

def cmd_review_shot(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    try:
        from cli.review import create_shot_review_report
        from shot_review import ShotReviewError

        report = create_shot_review_report(args)
        report["path"] = str(Path(report["path"]).resolve())
    except (ShotReviewError, MediaQAError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit({"ok": True, "approved": report["approved"], "review": report})
    return 0


def cmd_review_contract(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    if args.review_contract_action == "upgrade-v3":
        manifest["review_contract_version"] = 3
        save_manifest(root, manifest)
        emit(
            {
                "ok": True,
                "review_contract_version": 3,
                "note": "Future review-final calls require watched_full, grades, and canonical fail reasons.",
            }
        )
        return 0
    if args.review_contract_action != "migrate":
        raise FilmError(f"unknown review-contract action: {args.review_contract_action}")
    from cli.review import migrate_review_contract

    legacy, _migrated_at = migrate_review_contract(manifest)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "review_contract_version": 2,
            "pending_shot_reviews": legacy,
            "note": "existing approvals remain historical records; review each listed clip before it can satisfy v1.6 delivery gates",
        }
    )
    return 0


def cmd_external_review(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from external_review import ExternalReviewError, capability_probe, create_report

    try:
        if args.external_review_action == "probe":
            report = capability_probe()
        else:
            report = create_report(
                args.root,
                video=args.video,
                subtitles=args.subtitles,
                director_contract=args.director_contract,
                sanitized_frame_index=args.sanitized_frame_index,
                sanitized=bool(args.sanitized),
                purpose=args.purpose,
            )
    except ExternalReviewError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0


def cmd_visual_text_audit(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from visual_text_audit import VisualTextAuditError, audit_clip

    try:
        report = audit_clip(
            args.root,
            args.source,
            base_url=args.base_url,
            model=args.model,
            token=os.environ.get("AIFILM_LOCAL_OMNI_TOKEN") or None,
        )
    except VisualTextAuditError as exc:
        raise FilmError(f"VISUAL_TEXT_AUDIT_ERROR: {exc}") from exc
    emit(report)
    return 0 if report["status"] == "clean" else 2


def cmd_visual_text_repair(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from visual_text_repair import VisualTextRepairError, repair_clip

    try:
        report = repair_clip(
            args.root, args.source, base_url=args.base_url, audit_path=args.audit_receipt
        )
    except VisualTextRepairError as exc:
        raise FilmError(f"VISUAL_TEXT_REPAIR_ERROR: {exc}") from exc
    emit(report)
    return 0

