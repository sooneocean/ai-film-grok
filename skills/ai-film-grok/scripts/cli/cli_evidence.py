"""Evidence / state-index CLI cluster — extracted from aifilm_grok (public cmd strings unchanged).

Commands: state-index | promotion-report | production-evidence | speech-preview
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from util.errors import FilmError


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def add_evidence_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pe = sub.add_parser("production-evidence", help="Read-only production evidence ledger")
    pe.add_argument("--root", required=True)

    promotion = sub.add_parser(
        "promotion-report",
        help="Read-only candidate-to-promotion quality report",
    )
    promotion.add_argument("--root", required=True)
    promotion.add_argument(
        "--out", default=None, help="Explicit JSON report path inside the film root"
    )


    speech_preview = sub.add_parser(
        "speech-preview",
        help="Private RTX 5090 speech preview sidecar; candidate-only, never a production TTS backend",
    )
    speech_preview_sub = speech_preview.add_subparsers(dest="speech_preview_action", required=True)
    speech_preview_sub.add_parser(
        "probe",
        help="Validate loopback launcher and capacity-check configuration; never starts inference",
    )
    speech_start = speech_preview_sub.add_parser(
        "start", help="Request the configured private launcher after a live capacity gate"
    )
    speech_start.add_argument(
        "--confirm", action="store_true", help="Required to launch the sidecar"
    )
    speech_session = speech_preview_sub.add_parser(
        "session", help="Record one decoded, measured dialogue turn as a candidate-only receipt"
    )
    speech_session.add_argument("--root", required=True, help="Film workspace root")
    speech_session.add_argument(
        "--audio", required=True, help="Decoded reply audio inside the workspace"
    )
    speech_session.add_argument(
        "--session-json", required=True, help="In-workspace measured client result JSON"
    )
    speech_export = speech_preview_sub.add_parser(
        "export-candidate", help="Export a hash-bound preview candidate for human listening"
    )
    speech_export.add_argument("--root", required=True, help="Film workspace root")
    speech_export.add_argument(
        "--session-receipt", required=True, help="In-workspace speech-preview session receipt"
    )

    si = sub.add_parser(
        "state-index",
        help="Checkpoint: state photos + keyframes + promote plan (fluid camera/joins)",
    )
    si_sub = si.add_subparsers(dest="state_index_action", required=True)
    sic = si_sub.add_parser(
        "check",
        help="Run state-index gate; write receipts/state-index.json",
    )
    sic.add_argument("--root", required=True)
    sic.add_argument(
        "--strict",
        action="store_true",
        help="Also fail if generate_plan or soft gaps non-empty",
    )
    sip = si_sub.add_parser(
        "plan",
        help="Print regenerate plan (state photos / keyframes / promote) for this stage",
    )
    sip.add_argument("--root", required=True)
    sip.add_argument("--strict", action="store_true")
    sia = si_sub.add_parser(
        "approve-state",
        help="Register a human-approved local I2I wardrobe-state image; never calls a provider",
    )
    sia.add_argument("--root", required=True)
    sia.add_argument("--character-id", required=True)
    sia.add_argument("--wardrobe-state-id", required=True)
    sia.add_argument("--image", required=True)
    sia.add_argument("--reviewer", required=True)
    sia.add_argument("--review-note", required=True)
    sia.add_argument(
        "--generation-receipt",
        help="JSON receipt for this I2I generation; required for non-full states",
    )
    sipf = si_sub.add_parser(
        "approve-performance-state",
        help="Register a human-approved, hash-bound dialogue performance I2I still",
    )
    sipf.add_argument("--root", required=True)
    sipf.add_argument("--speaker", required=True)
    sipf.add_argument("--performance-state-id", required=True)
    sipf.add_argument("--image", required=True)
    sipf.add_argument("--generation-receipt", required=True)
    sipf.add_argument("--reviewer", required=True)
    sipf.add_argument("--review-note", required=True)
    sis = si_sub.add_parser(
        "contact-sheet",
        help="Render an offline visual review sheet for one wardrobe ladder; never calls a provider",
    )
    sis.add_argument("--root", required=True)
    sis.add_argument("--character-id", required=True)


def cmd_state_index(args: argparse.Namespace) -> int:
    """Checkpoint: state photos + keyframes + promote plan for fluid transitions."""
    skill_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from state_index_gate import run_state_index_check, write_state_index_receipt
    except ImportError as exc:
        raise FilmError(f"Cannot import state_index_gate: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    action = getattr(args, "state_index_action", None) or "check"
    if action == "approve-performance-state":
        from performance_state import approve_performance_state

        try:
            receipt = approve_performance_state(
                root,
                speaker=str(args.speaker),
                state_id=str(args.performance_state_id),
                image=Path(args.image),
                generation_receipt=Path(args.generation_receipt),
                reviewer=str(args.reviewer),
                review_note=str(args.review_note),
            )
        except ValueError as exc:
            raise FilmError(str(exc)) from exc
        _emit({"ok": True, **receipt})
        return 0
    if action == "approve-state":
        from visual_bible import load_bible, save_bible
        from wardrobe_ladder import approve_state

        bible = load_bible(root)
        try:
            state = approve_state(
                bible,
                str(args.character_id),
                str(args.wardrobe_state_id),
                Path(args.image),
                root=root,
                reviewer=str(args.reviewer),
                review_note=str(args.review_note),
                generation_receipt=(
                    Path(args.generation_receipt) if args.generation_receipt else None
                ),
            )
        except ValueError as exc:
            raise FilmError(str(exc)) from exc
        save_bible(root, bible)
        _emit(
            {
                "ok": True,
                "kind": "wardrobe-state-approved",
                "character_id": args.character_id,
                "state": state,
            }
        )
        return 0
    if action == "contact-sheet":
        from visual_bible import load_bible
        from wardrobe_ladder import render_contact_sheet

        try:
            sheet = render_contact_sheet(load_bible(root), str(args.character_id), root=root)
        except ValueError as exc:
            raise FilmError(str(exc)) from exc
        _emit(
            {
                "ok": True,
                "kind": "wardrobe-ladder-contact-sheet",
                "character_id": args.character_id,
                **sheet,
            }
        )
        return 0
    report = run_state_index_check(root)
    path = write_state_index_receipt(root, report)
    report["receipt_path"] = str(path)
    if action == "plan":
        # plan = full report + human-readable generate_plan first
        plan_view = {
            "ok": report.get("ok"),
            "kind": "state-index-plan",
            "purpose": report.get("purpose"),
            "generate_plan": report.get("generate_plan") or [],
            "agent_do": report.get("agent_do") or [],
            "hard": report.get("hard") or [],
            "soft": report.get("soft") or [],
            "fluency_issues": report.get("fluency_issues") or [],
            "undress_anchor": report.get("undress_anchor"),
            "missing_state_photos": report.get("missing_state_photos"),
            "exact_state_ids": report.get("exact_state_ids") or {},
            "missing_keyframes": report.get("missing_keyframes"),
            "receipt_path": str(path),
            "ref": report.get("ref"),
            "note": (
                "Execute generate_plan in order, then re-run: "
                f'aifilm state-index check --root "{root}"'
            ),
        }
        _emit(plan_view)
    else:
        _emit(report)
    if not report.get("ok"):
        return 2
    if getattr(args, "strict", False) and (report.get("generate_plan") or report.get("soft")):
        return 3
    return 0



def cmd_promotion_report(args: argparse.Namespace) -> int:
    from promotion_report import build_promotion_report, write_promotion_report

    root = Path(args.root).expanduser().resolve()
    try:
        report = (
            write_promotion_report(root, args.out)
            if getattr(args, "out", None)
            else build_promotion_report(root)
        )
    except (OSError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0



def cmd_production_evidence(args: argparse.Namespace) -> int:
    """Read-only evidence ledger for production gates."""
    from production_evidence import build_evidence

    report = build_evidence(Path(args.root).expanduser().resolve())
    _emit(report)
    return 0



def cmd_speech_preview(args: argparse.Namespace) -> int:
    """Operate the private, candidate-only Speech-to-Speech preview sidecar."""
    from speech_preview import SpeechPreviewError, export_candidate, probe, record_session, start

    try:
        if args.speech_preview_action == "probe":
            report = probe()
        elif args.speech_preview_action == "start":
            report = start(confirm=bool(args.confirm))
        elif args.speech_preview_action == "session":
            report = record_session(args.root, audio=args.audio, session_json=args.session_json)
        else:
            report = export_candidate(args.root, session_receipt=args.session_receipt)
    except SpeechPreviewError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0 if report.get("ok", True) else 2


