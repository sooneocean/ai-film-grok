"""Provenance-aware dialogue screenplay drafting and review gates."""

from __future__ import annotations

from typing import Any


def build_dialogue_screenplay(normalized: dict[str, Any]) -> dict[str, Any]:
    genre, story_mode = str(normalized.get("genre") or ""), str(normalized.get("story_mode") or "")
    exception = (
        "documentary"
        if genre == "documentary"
        else "explicit_monologue"
        if story_mode == "monologue" and normalized.get("explicit_monologue")
        else None
    )
    mode = (
        "storyteller"
        if exception == "documentary"
        else "monologue"
        if exception
        else "dialogue_drama"
    )
    refs, blocks = (
        list(normalized.get("source_evidence_refs") or []),
        list(normalized.get("dialogue_blocks") or []),
    )
    scenes = []
    for index, chunk in enumerate(normalized.get("scene_chunks") or [], 1):
        body = str((chunk or {}).get("body") or normalized.get("raw_excerpt") or "")
        turns = []
        if not exception:
            source = blocks if index == 1 else []
            if source:
                for line_index, block in enumerate(source, 1):
                    text, language = (
                        str(block.get("text") or ""),
                        str(block.get("language") or "zh"),
                    )
                    turns.append(
                        {
                            "line_id": str(block.get("id") or f"line_{line_index:02d}"),
                            "speaker": str(block.get("speaker") or "pending_cast"),
                            "addressee": str(block.get("addressee") or ""),
                            "dialogue_zh": str(
                                block.get("subtitle_zh") or text if language == "ja" else text
                            ),
                            "dialogue_ja": text if language == "ja" else "",
                            "subtitle_zh": str(
                                block.get("subtitle_zh") or (text if language != "ja" else "")
                            ),
                            "translation_status": "ready" if language == "ja" else "pending",
                            "provenance": "source_supported",
                            "source_evidence": {"source_refs": refs, "source_excerpt": text},
                        }
                    )
            elif body:
                turns.append(
                    {
                        "line_id": f"scene{index:02d}_line01",
                        "speaker": "pending_cast",
                        "addressee": "",
                        "dialogue_zh": body,
                        "dialogue_ja": "",
                        "subtitle_zh": "",
                        "translation_status": "pending",
                        "provenance": "creative_suggestion",
                        "source_evidence": {"source_refs": refs, "source_excerpt": body},
                    }
                )
        scenes.append(
            {
                "scene_id": f"scene_{index:02d}",
                "scene_goal": "",
                "conflict": "",
                "emotional_turn": "",
                "time_space": {},
                "dialogue_turns": turns,
                "coverage_intent": [],
                "narration_gaps": [],
                "review_status": "pending",
            }
        )
    return {
        "schema_version": 1,
        "kind": "dialogue-screenplay",
        "mode": mode,
        "mode_exception": exception,
        "status": "candidate_only",
        "review_status": "pending",
        "source_refs": refs,
        "scenes": scenes,
        "narration_gaps": [],
    }


def validate_dialogue_screenplay(screenplay: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    scenes = screenplay.get("scenes") if isinstance(screenplay.get("scenes"), list) else []
    turns = [
        turn
        for scene in scenes
        if isinstance(scene, dict)
        for turn in scene.get("dialogue_turns", [])
        if isinstance(turn, dict)
    ]
    gaps = list(screenplay.get("narration_gaps") or [])
    if strict and (
        screenplay.get("status") != "reviewed" or screenplay.get("review_status") != "approved"
    ):
        issues.append(
            {
                "code": "SCREENPLAY_REVIEW_REQUIRED",
                "message": "screenplay must be approved",
                "node_ref": "screenplay",
            }
        )
    for turn in turns:
        if strict and (not turn.get("dialogue_ja") or turn.get("translation_status") != "ready"):
            issues.append(
                {
                    "code": "DIALOGUE_TRANSLATION_PENDING",
                    "message": "Japanese dialogue is not ready",
                    "node_ref": str(turn.get("line_id")),
                }
            )
        evidence = turn.get("source_evidence") or {}
        if strict and not evidence.get("source_refs"):
            issues.append(
                {
                    "code": "SOURCE_EVIDENCE_REQUIRED",
                    "message": "source evidence is required",
                    "node_ref": str(turn.get("line_id")),
                }
            )
    dialogue_text = {
        str(turn.get("subtitle_zh") or turn.get("dialogue_zh") or "") for turn in turns
    }
    narration_duration = 0.0
    for gap in gaps:
        narration_duration += float(gap.get("duration_sec") or 0)
        ref = str(gap.get("gap_id") or "narration")
        if strict and not gap.get("narration_reason"):
            issues.append(
                {
                    "code": "NARRATION_REASON_REQUIRED",
                    "message": "narration needs a reason",
                    "node_ref": ref,
                }
            )
        if strict and not gap.get("uncovered_information"):
            issues.append(
                {
                    "code": "NARRATION_INFORMATION_GAP_REQUIRED",
                    "message": "narration needs uncovered information",
                    "node_ref": ref,
                }
            )
        if strict and (
            str(gap.get("text_zh") or "") in dialogue_text
            or gap.get("duplicates_dialogue_or_visual")
        ):
            issues.append(
                {
                    "code": "NARRATION_DUPLICATES_STORY",
                    "message": "narration duplicates story",
                    "node_ref": ref,
                }
            )
    ratio = narration_duration / max(
        5.0, sum(float(turn.get("duration_sec") or 0) for turn in turns) + narration_duration
    )
    if strict and ratio > 0.15:
        issues.append(
            {
                "code": "NARRATION_BUDGET_EXCEEDED",
                "message": "narration exceeds dialogue budget",
                "node_ref": "screenplay",
            }
        )
    return {
        "ok": not issues,
        "issues": issues,
        "metrics": {
            "scenes": len(scenes),
            "dialogue_turns": len(turns),
            "narration_ratio": round(ratio, 3),
            "candidate_only": screenplay.get("status") == "candidate_only",
        },
    }
