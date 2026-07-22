#!/usr/bin/env python3
"""Evidence separation: intent vs executed vs human review (codex ledger idea).

Does not invent a full Director Contract. Classifies existing receipts so a plan
or empty stub cannot impersonate delivery.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json


def _present(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 2


def classify_evidence(root: Path) -> dict[str, Any]:
    """Split film-root artifacts into intent / executed / human_review buckets.

    Returns structured status for `aifilm status` and preflight soft notes.
    """
    root = Path(root).expanduser().resolve()
    receipts = root / "receipts"

    # --- intent / plan (authoring; not proof of delivery) ---
    intent: dict[str, Any] = {
        "class": "intent",
        "film_spec": _present(root / "film-spec.json"),
        "style_bible": _present(root / "style-bible.json"),
        "sound_plan": False,
        "transition_intents": False,
        "timeline": _present(root / "timeline.json"),
        "continuity_chain_doc": _present(root / "continuity_chain.md"),
    }
    spec = read_json(root / "film-spec.json") or {}
    if isinstance(spec.get("sound_plan"), dict) and spec["sound_plan"]:
        intent["sound_plan"] = True
    if isinstance(spec.get("transition_intents"), list) and spec["transition_intents"]:
        intent["transition_intents"] = True
    style = read_json(root / "style-bible.json") or {}
    intent["style_locked"] = bool(style.get("locked"))

    # --- executed (machine produced artifacts with substance) ---
    mix = read_json(receipts / "mix_report.json") if receipts.is_dir() else None
    tts_reh = read_json(receipts / "tts-rehearsal.json") if receipts.is_dir() else None
    preview = read_json(receipts / "compose-preview.json") if receipts.is_dir() else None
    queue = read_json(receipts / "media-queue.json") if receipts.is_dir() else None
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    final_rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    silent_rec = outputs.get("silent_film") if isinstance(outputs.get("silent_film"), dict) else {}

    def _record_executed(rec: dict[str, Any] | None) -> bool:
        if not isinstance(rec, dict) or not rec:
            return False
        # empty stub: only path keys with missing files
        path = rec.get("path")
        if path and Path(str(path)).is_file():
            return True
        if rec.get("sha256") and rec.get("duration_sec"):
            return True
        qa = rec.get("technical_qa")
        return bool(isinstance(qa, dict) and qa.get("ok") is True)

    executed: dict[str, Any] = {
        "class": "executed",
        "tts_rehearsal": bool(
            isinstance(tts_reh, dict)
            and tts_reh.get("ok") is True
            and (tts_reh.get("shots") or tts_reh.get("shot_count"))
        ),
        "tts_rehearsal_path": str(receipts / "tts-rehearsal.json")
        if isinstance(tts_reh, dict)
        else None,
        "mix_report": bool(isinstance(mix, dict) and mix.get("ok") is not False and mix),
        "final_film": _record_executed(final_rec),
        "silent_film": _record_executed(silent_rec),
        "compose_preview": bool(
            isinstance(preview, dict)
            and preview.get("ok") is True
            and (preview.get("url") or preview.get("studio_url"))
        ),
        "media_queue": bool(isinstance(queue, dict) and (queue.get("jobs") or queue.get("items"))),
        "approved_clip_count": sum(
            1
            for rec in (man.get("clips") or {}).values()
            if isinstance(rec, dict) and rec.get("status") == "approved"
        ),
    }

    # --- human review (must not be agent self-approval alone) ---
    pilot = read_json(receipts / "pilot-approval.json") if receipts.is_dir() else None
    pilot_score = read_json(receipts / "pilot-scorecard.json") if receipts.is_dir() else None
    final_review = (
        outputs.get("final_review") if isinstance(outputs.get("final_review"), dict) else None
    )
    try:
        from production_gates import pilot_is_user_approved

        pilot_user = pilot_is_user_approved(pilot) if pilot else False
    except Exception:
        pilot_user = bool(
            isinstance(pilot, dict)
            and str(pilot.get("approved_by") or "").lower() == "user"
            and str(pilot.get("user_phrase") or "").strip()
        )

    human: dict[str, Any] = {
        "class": "human_review",
        "pilot_user_approved": pilot_user,
        "pilot_scorecard": bool(isinstance(pilot_score, dict) and pilot_score),
        "final_review_approved": bool(
            isinstance(final_review, dict) and final_review.get("approved") is True
        ),
        "final_reviewer": (final_review or {}).get("reviewer")
        if isinstance(final_review, dict)
        else None,
    }

    # Impersonation guards
    risks: list[dict[str, str]] = []
    if intent["sound_plan"] and not executed["mix_report"] and not executed["final_film"]:
        risks.append(
            {
                "code": "SOUND_PLAN_NOT_EXECUTED",
                "message": "sound_plan is intent only — no mix_report/final_film yet",
            }
        )
    if intent["transition_intents"] and not executed["final_film"] and not executed["silent_film"]:
        risks.append(
            {
                "code": "TRANSITION_INTENT_NOT_EXECUTED",
                "message": "transition_intents are plan — not proof of assembled plate",
            }
        )
    if executed.get("compose_preview") is False and _present(receipts / "compose-preview.json"):
        risks.append(
            {
                "code": "PREVIEW_STUB",
                "message": "compose-preview.json present but not a valid executed preview",
            }
        )
    if isinstance(final_rec, dict) and final_rec and not executed["final_film"]:
        risks.append(
            {
                "code": "FINAL_STUB",
                "message": "final_film record exists but path/qa not executed",
            }
        )
    if human["final_review_approved"] and not executed["final_film"]:
        risks.append(
            {
                "code": "REVIEW_WITHOUT_FINAL",
                "message": "human review claim without executed final_film",
            }
        )

    # craft-spine receipts (optional)
    craft_receipts = {
        "creative_brief": _present(receipts / "creative-brief.md"),
        "beat_sheet": _present(receipts / "beat-sheet.md"),
        "selects_report": _present(receipts / "selects-report.json"),
        "rough_cut": _present(receipts / "rough-cut.json"),
        "lipsync_canary": _present(receipts / "lipsync-canary.json"),
        "tts_ab": any(receipts.glob("tts-ab/manifest-*.json")) if receipts.is_dir() else False,
    }
    intent["craft_receipts"] = craft_receipts

    craft_map = {
        "idea": craft_receipts["creative_brief"] or intent.get("film_spec"),
        "story": intent.get("film_spec"),
        "beats": craft_receipts["beat_sheet"] or intent.get("film_spec"),
        "shots": intent.get("film_spec") and intent.get("style_locked"),
        "media": executed.get("media_queue") or executed.get("approved_clip_count", 0) > 0,
        "selects": craft_receipts["selects_report"] or executed.get("approved_clip_count", 0) > 0,
        "rough": craft_receipts["rough_cut"]
        or executed.get("silent_film")
        or executed.get("final_film"),
        "verified": human.get("final_review_approved") and executed.get("final_film"),
    }

    return {
        "intent": intent,
        "executed": executed,
        "human_review": human,
        "impersonation_risks": risks,
        "craft_rings": craft_map,
        "note": (
            "intent ≠ executed ≠ human_review. "
            "film-spec / sound_plan / transition_intents are plans; "
            "tts-rehearsal / mix_report / final_film are executed; "
            "pilot-approval / review-final are human. "
            "craft_rings map Idea→Verified (see references/craft-spine.md). "
            "See references/lessons-2026-07-20-sediment-cn-codex.md"
        ),
    }
