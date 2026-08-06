"""Pilot CLI cluster — extracted from aifilm_grok (public cmd strings unchanged).

Commands: ``pilot pick|report|pack|score|approve`` (+ hyphen alias via workflow).
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


def add_pilot_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pilot = sub.add_parser(
        "pilot",
        help="Pilot three-shot scorecard assist (pick/report/score/approve)",
    )
    pilot_sub = pilot.add_subparsers(dest="pilot_action", required=True)
    pp = pilot_sub.add_parser("pick", help="Suggest pilot shot ids from film-spec beats")
    pp.add_argument("--root", required=True)
    pp.add_argument("--n", type=int, default=3)
    pr = pilot_sub.add_parser("report", help="Media + scorecard + approval status for pilot shots")
    pr.add_argument("--root", required=True)
    pr.add_argument("--shots", default="", help="Comma shot ids (default auto-pick)")
    pk = pilot_sub.add_parser(
        "pack",
        help="Pilot GO pack: 3 shots + adult three-beat + heat/state → receipts/pilot-go.json",
    )
    pk.add_argument("--root", required=True)
    pk.add_argument("--shots", default="", help="Comma shot ids (default auto-pick)")
    ps = pilot_sub.add_parser(
        "score", help="Write receipts/pilot-scorecard.json (identity/style/motion)"
    )
    ps.add_argument("--root", required=True)
    ps.add_argument("--shots", required=True)
    ps.add_argument("--reviewer", required=True)
    ps.add_argument("--notes", required=True)
    ps.add_argument("--score-identity", required=True, choices=["pass", "fail"])
    ps.add_argument("--score-style", required=True, choices=["pass", "fail"])
    ps.add_argument("--score-motion", required=True, choices=["pass", "fail"])
    ps.add_argument(
        "--no-notes-on-fail",
        action="store_true",
        help="Do not open director_notes when pilot score fails",
    )
    pa = pilot_sub.add_parser("approve", help="Write user pilot-approval.json (needs user phrase)")
    pa.add_argument("--root", required=True)
    pa.add_argument("--shots", default="")
    pa.add_argument("--user-phrase", required=True, help='User words e.g. "pilot 过"')
    pa.add_argument("--notes", default="")
    pa.add_argument("--compared-to-cast", default=None)
    pa.add_argument(
        "--no-require-scorecard",
        action="store_true",
        help="Allow without pilot-scorecard all-pass (not recommended)",
    )


def cmd_pilot(args: argparse.Namespace) -> int:
    """Pilot three-shot scorecard assist (pick/report/score/approve)."""
    skill_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from pilot_review import (
            PilotReviewError,
            build_pilot_approval,
            build_pilot_scorecard,
            load_pilot_scorecard,
            pick_pilot_shots,
            pilot_report,
            read_json,
            write_pilot_approval,
            write_pilot_scorecard,
        )
        from production_gates import pilot_is_user_approved
    except ImportError as exc:
        raise FilmError(f"Cannot import pilot_review: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True)
    if not cinematic.get("ok"):
        raise FilmError(
            "pilot blocked by cinematic audit ["
            + ", ".join(cinematic.get("blocking_codes") or [])
            + "]"
        )
    action = str(getattr(args, "pilot_action", "") or "")
    try:
        if action == "pick":
            spec = read_json(root / "film-spec.json")
            if not spec:
                raise FilmError("film-spec.json missing")
            shots = pick_pilot_shots(spec, n=int(getattr(args, "n", 3) or 3))
            _emit({"ok": True, "shots": shots, "n": len(shots)})
            return 0
        if action == "report":
            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            _emit(pilot_report(root, shots=shots))
            return 0
        if action == "pack":
            from pilot_pack import pilot_pack

            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            _emit(pilot_pack(root, shots=shots))
            return 0
        if action == "score":
            from pilot_review import fail_scorecard_to_director_notes

            shots = [s.strip() for s in str(args.shots).split(",") if s.strip()]
            scores = {
                "identity": args.score_identity,
                "style": args.score_style,
                "motion": args.score_motion,
            }
            card = build_pilot_scorecard(
                shots=shots,
                scores=scores,
                reviewer=str(args.reviewer),
                notes=str(args.notes),
            )
            path = write_pilot_scorecard(root, card)
            notes_items = fail_scorecard_to_director_notes(
                root,
                card,
                enabled=not bool(getattr(args, "no_notes_on_fail", False)),
            )
            _emit(
                {
                    "ok": True,
                    "path": str(path),
                    "scorecard": card,
                    "director_notes_items": notes_items,
                }
            )
            return 0
        if action == "approve":
            scorecard = load_pilot_scorecard(root)
            shots = [
                s.strip() for s in str(getattr(args, "shots", "") or "").split(",") if s.strip()
            ]
            if not shots and isinstance(scorecard.get("shots"), list):
                shots = [str(x) for x in scorecard["shots"]]
            if not shots:
                spec = read_json(root / "film-spec.json")
                shots = pick_pilot_shots(spec) if spec else []
            approval = build_pilot_approval(
                shots=shots,
                user_phrase=str(args.user_phrase),
                notes=str(getattr(args, "notes", "") or ""),
                compared_to_cast=getattr(args, "compared_to_cast", None),
                scorecard=scorecard or None,
                require_scorecard=not bool(getattr(args, "no_require_scorecard", False)),
            )
            routing = read_json(root / "receipts" / "i2v-routing.json")
            if routing:
                approval["i2v_routing"] = {
                    "selected_provider": routing.get("selected_provider"),
                    "requested_profile": routing.get("requested_profile"),
                }
            path = write_pilot_approval(root, approval)
            _emit(
                {
                    "ok": True,
                    "path": str(path),
                    "approval": approval,
                    "user_approved": pilot_is_user_approved(approval),
                }
            )
            return 0
        raise FilmError(f"Unknown pilot action: {action}")
    except PilotReviewError as exc:
        raise FilmError(str(exc)) from exc
