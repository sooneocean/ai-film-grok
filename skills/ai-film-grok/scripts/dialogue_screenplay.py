"""Pure, evidence-bearing dialogue screenplay contracts."""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1
KIND = "dialogue-screenplay"
NARRATION_LIMIT = 0.15
NARRATION_REASONS = frozenset({"time_jump", "location_context", "offscreen_fact", "inner_context"})
PROVENANCE = frozenset({"source_supported", "creative_suggestion"})
APPROVED = frozenset({"reviewed", "approved", "locked"})
PENDING_MARKERS = ("待确认", "待定", "pending", "unknown")


def _text(value: object) -> str:
    return str(value or "").strip()


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _evidence(refs: list[str], excerpt: str, provenance: str) -> dict[str, Any]:
    return {
        "source_refs": list(refs),
        "source_excerpt": excerpt,
        "provenance": provenance,
    }


def _has_kana(value: object) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", _text(value)))


def _first_sentence(value: object) -> str:
    source = _text(value)
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?])\s*|\n+", source) if part.strip()]
    return parts[0] if parts else source


def _select_mode(normalized: dict[str, Any]) -> tuple[str, str | None]:
    genre = _text(normalized.get("genre")).lower()
    requested = _text(normalized.get("story_mode") or normalized.get("screenplay_mode")).lower()
    if genre == "documentary" or requested == "documentary":
        return "storyteller", "documentary"
    if normalized.get("explicit_monologue") is True or requested in {
        "monologue",
        "storyteller",
    }:
        return "monologue", "explicit_monologue"
    return "dialogue_drama", None


def _source_refs(normalized: dict[str, Any], reception: dict[str, Any] | None) -> list[str]:
    refs = _strings(normalized.get("source_evidence_refs"))
    if isinstance(reception, dict):
        source = reception.get("source")
        if isinstance(source, dict) and _text(source.get("source_ref")):
            refs.append(_text(source["source_ref"]))
        refs.extend(_strings(reception.get("source_refs")))
    return list(dict.fromkeys(refs))


def _explicit_turn(block: dict[str, Any], index: int, refs: list[str]) -> dict[str, Any]:
    raw = _text(block.get("text") or block.get("dialogue") or block.get("dialogue_zh"))
    language = _text(block.get("language")).lower()
    dialogue_ja = _text(block.get("dialogue_ja"))
    if not dialogue_ja and (language.startswith("ja") or _has_kana(raw)):
        dialogue_ja = raw
    subtitle_zh = _text(block.get("subtitle_zh") or block.get("caption_text"))
    dialogue_zh = _text(block.get("dialogue_zh"))
    if not dialogue_zh and not dialogue_ja:
        dialogue_zh = raw
    subtitle_zh = subtitle_zh or dialogue_zh
    excerpt = _text(block.get("source_excerpt")) or raw or subtitle_zh
    block_refs = _strings(block.get("source_refs")) or refs
    provenance = _text(block.get("provenance")) or "source_supported"
    if provenance not in PROVENANCE:
        provenance = "creative_suggestion"
    return {
        "line_id": _text(block.get("id") or block.get("line_id")) or f"line_{index:03d}",
        "speaker": _text(block.get("speaker")) or "pending_cast",
        "addressee": _text(block.get("addressee")) or "pending_addressee",
        "dialogue_zh": dialogue_zh or subtitle_zh,
        "subtitle_zh": subtitle_zh,
        "dialogue_ja": dialogue_ja,
        "translation_status": _text(block.get("translation_status"))
        or ("ready" if dialogue_ja and subtitle_zh else "pending"),
        "emotion": _text(block.get("emotion")) or "待确认",
        "subtext": _text(block.get("subtext")) or "待确认",
        "actions": {
            "before": _text(block.get("action_before")),
            "during": _text(block.get("action_during")),
            "after": _text(block.get("action_after")),
        },
        "gaze": _text(block.get("gaze")) or "待确认",
        "props": _strings(block.get("props")),
        "state_delta": _text(block.get("state_delta")) or "待确认",
        "duration_sec": float(block.get("duration_sec") or 0),
        "provenance": provenance,
        "source_evidence": _evidence(block_refs, excerpt, provenance),
        "review_status": _text(block.get("review_status")) or "pending",
    }


def _prose_candidate(body: str, line_id: str, refs: list[str]) -> dict[str, Any]:
    # The source sentence remains byte-for-byte; only its proposed use as
    # speech is creative, so no new fact is smuggled into the story.
    excerpt = _first_sentence(body)
    return {
        "line_id": line_id,
        "speaker": "pending_cast",
        "addressee": "pending_addressee",
        "dialogue_zh": excerpt,
        "subtitle_zh": excerpt,
        "dialogue_ja": "",
        "translation_status": "pending",
        "emotion": "待确认",
        "subtext": "待确认",
        "actions": {"before": "", "during": "", "after": ""},
        "gaze": "待确认",
        "props": [],
        "state_delta": "待确认",
        "duration_sec": 0.0,
        "provenance": "creative_suggestion",
        "source_evidence": _evidence(refs, excerpt, "creative_suggestion"),
        "review_status": "pending",
    }


def build_dialogue_screenplay(
    normalized: dict[str, Any],
    reception: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an unapproved screenplay candidate without I/O or input mutation."""
    if not isinstance(normalized, dict):
        raise TypeError("normalized must be an object")
    refs = _source_refs(normalized, reception)
    mode, exception = _select_mode(normalized)
    chunks = [
        chunk for chunk in (normalized.get("scene_chunks") or []) if isinstance(chunk, dict)
    ] or [
        {
            "title": "Main",
            "body": _text(normalized.get("raw_excerpt") or normalized.get("logline")),
        }
    ]
    blocks = [
        block for block in (normalized.get("dialogue_blocks") or []) if isinstance(block, dict)
    ]
    scenes: list[dict[str, Any]] = []
    unbound_index = 0
    for scene_index, chunk in enumerate(chunks, 1):
        scene_id = _text(chunk.get("id")) or f"scene_{scene_index:03d}"
        body = _text(chunk.get("body"))
        bound = [
            block
            for block in blocks
            if _text(block.get("scene_id")) in {scene_id, _text(chunk.get("id"))}
        ]
        if not bound and len(chunks) == 1:
            bound = blocks
        elif not bound and blocks:
            remaining_scenes = len(chunks) - scene_index + 1
            remaining_blocks = len(blocks) - unbound_index
            take = max(0, (remaining_blocks + remaining_scenes - 1) // remaining_scenes)
            bound = blocks[unbound_index : unbound_index + take]
        unbound_index += len(bound)
        turns = [
            _explicit_turn(block, unbound_index - len(bound) + offset, refs)
            for offset, block in enumerate(bound, 1)
        ]
        if mode == "dialogue_drama" and not turns and body:
            turns = [_prose_candidate(body, f"line_{scene_index:03d}_001", refs)]
        scenes.append(
            {
                "scene_id": scene_id,
                "title": _text(chunk.get("title")) or f"Scene {scene_index}",
                "scene_goal": _text(chunk.get("scene_goal") or chunk.get("goal"))
                or "待确认：场景目标",
                "conflict": _text(chunk.get("conflict")) or "待确认：场景冲突",
                "emotional_turn": _text(chunk.get("emotional_turn")) or "待确认：情绪转折",
                "time_space": {
                    "time": _text(chunk.get("time")) or "待确认",
                    "location": _text(chunk.get("location")) or "待确认",
                },
                "field_provenance": {
                    "scene_goal": _text(chunk.get("scene_goal_provenance"))
                    or "creative_suggestion",
                    "conflict": _text(chunk.get("conflict_provenance")) or "creative_suggestion",
                    "emotional_turn": _text(chunk.get("emotional_turn_provenance"))
                    or "creative_suggestion",
                    "time_space": _text(chunk.get("time_space_provenance"))
                    or "creative_suggestion",
                },
                "dialogue_turns": turns if mode == "dialogue_drama" else [],
                "coverage_intent": {
                    "shot_reverse_shot": mode == "dialogue_drama",
                    "over_shoulder": mode == "dialogue_drama",
                    "reaction": mode == "dialogue_drama",
                    "action_cover": mode == "dialogue_drama",
                    "environment_insert": True,
                },
                "narration_gaps": [],
                "source_evidence": _evidence(refs, body, "source_supported"),
                "review_status": "pending",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(normalized.get("title")),
        "mode": mode,
        "mode_exception": exception,
        "status": "candidate_only",
        "review_status": "pending",
        "source_refs": refs,
        "scenes": scenes,
        "narration_gaps": [],
        "authoring_questions": [
            "确认场景目标、冲突、情绪转折与时空",
            "确认说话人、受话人、表演动作与状态变化",
            "审核中文对白并完成日文口语翻译",
        ]
        if mode == "dialogue_drama"
        else [],
    }


def _issue(code: str, message: str, node_ref: str) -> dict[str, str]:
    return {"code": code, "message": message, "node_ref": node_ref}


def _pending(value: object) -> bool:
    value = _text(value).lower()
    return not value or any(marker in value for marker in PENDING_MARKERS)


def _check_evidence(value: object, node_ref: str, issues: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        issues.append(_issue("SOURCE_EVIDENCE_REQUIRED", "source_evidence is required", node_ref))
        return
    if not _strings(value.get("source_refs")) or not _text(value.get("source_excerpt")):
        issues.append(
            _issue(
                "SOURCE_EVIDENCE_REQUIRED",
                "source refs and excerpt are required",
                node_ref,
            )
        )
    if _text(value.get("provenance")) not in PROVENANCE:
        issues.append(_issue("SOURCE_PROVENANCE_INVALID", "source provenance is invalid", node_ref))


def _gaps(screenplay: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for gap in screenplay.get("narration_gaps") or []:
        if isinstance(gap, dict):
            key = _text(gap.get("gap_id")) or f"root_{len(result)}"
            seen.add(key)
            result.append((f"narration_gaps/{key}", gap))
    for scene in screenplay.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scene_id = _text(scene.get("scene_id")) or "unknown"
        for gap in scene.get("narration_gaps") or []:
            if isinstance(gap, dict):
                key = _text(gap.get("gap_id")) or f"{scene_id}_{len(result)}"
                if key not in seen:
                    seen.add(key)
                    result.append((f"scenes/{scene_id}/narration_gaps/{key}", gap))
    return result


def validate_dialogue_screenplay(screenplay: object, strict: bool = False) -> dict[str, Any]:
    """Validate shape and, in strict mode, narrative-lock readiness."""
    issues: list[dict[str, str]] = []
    if not isinstance(screenplay, dict):
        return {
            "ok": False,
            "issues": [_issue("SCREENPLAY_INVALID", "must be an object", "screenplay")],
            "metrics": {
                "scenes": 0,
                "dialogue_turns": 0,
                "narration_gaps": 0,
                "dialogue_duration_sec": 0.0,
                "narration_duration_sec": 0.0,
                "narration_ratio": 0.0,
                "candidate_only": False,
            },
        }
    if screenplay.get("schema_version") != SCHEMA_VERSION:
        issues.append(_issue("SCHEMA_VERSION_INVALID", "schema_version must be 1", "schema"))
    if screenplay.get("kind") != KIND:
        issues.append(_issue("KIND_INVALID", f"kind must be {KIND}", "kind"))
    mode = _text(screenplay.get("mode"))
    if mode not in {"dialogue_drama", "storyteller", "monologue"}:
        issues.append(_issue("MODE_INVALID", "unsupported screenplay mode", "mode"))
    scenes = screenplay.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        issues.append(_issue("SCENES_REQUIRED", "at least one scene is required", "scenes"))
        scenes = []
    if not isinstance(screenplay.get("narration_gaps"), list):
        issues.append(
            _issue("NARRATION_GAPS_INVALID", "narration_gaps must be an array", "narration")
        )
    if (
        strict
        and mode == "dialogue_drama"
        and (
            _text(screenplay.get("status")) not in APPROVED
            or _text(screenplay.get("review_status")) not in APPROVED
        )
    ):
        issues.append(
            _issue(
                "SCREENPLAY_REVIEW_REQUIRED",
                "screenplay must be reviewed before narrative lock",
                "screenplay",
            )
        )

    dialogue_duration = 0.0
    turn_count = 0
    dialogue_texts: set[str] = set()
    scene_keys = (
        "scene_id",
        "scene_goal",
        "conflict",
        "emotional_turn",
        "time_space",
        "dialogue_turns",
        "coverage_intent",
        "narration_gaps",
        "source_evidence",
        "review_status",
    )
    for index, scene in enumerate(scenes, 1):
        ref = (
            f"scenes/{_text(scene.get('scene_id')) or index}"
            if isinstance(scene, dict)
            else f"scenes/{index}"
        )
        if not isinstance(scene, dict):
            issues.append(_issue("SCENE_INVALID", "scene must be an object", ref))
            continue
        for key in scene_keys:
            if key not in scene:
                issues.append(_issue("SCENE_FIELD_REQUIRED", f"{key} is required", f"{ref}/{key}"))
        if strict and mode == "dialogue_drama":
            _check_evidence(scene.get("source_evidence"), ref, issues)
            if _text(scene.get("review_status")) not in APPROVED:
                issues.append(_issue("SCENE_REVIEW_REQUIRED", "scene must be reviewed", ref))
            for key in ("scene_goal", "conflict", "emotional_turn"):
                if _pending(scene.get(key)):
                    issues.append(
                        _issue(
                            "SCENE_AUTHORING_REQUIRED",
                            f"{key} must be authored",
                            f"{ref}/{key}",
                        )
                    )
            time_space = scene.get("time_space")
            if not isinstance(time_space, dict) or any(
                _pending(time_space.get(key)) for key in ("time", "location")
            ):
                issues.append(
                    _issue(
                        "SCENE_TIME_SPACE_REQUIRED",
                        "time and location must be authored",
                        f"{ref}/time_space",
                    )
                )
        turns = scene.get("dialogue_turns")
        if not isinstance(turns, list):
            issues.append(_issue("DIALOGUE_TURNS_INVALID", "must be an array", ref))
            turns = []
        if strict and mode == "dialogue_drama" and not turns:
            issues.append(_issue("DIALOGUE_COVERAGE_REQUIRED", "dialogue is required", ref))
        for turn_index, turn in enumerate(turns, 1):
            turn_count += 1
            turn_ref = (
                f"{ref}/dialogue_turns/{_text(turn.get('line_id')) or turn_index}"
                if isinstance(turn, dict)
                else f"{ref}/dialogue_turns/{turn_index}"
            )
            if not isinstance(turn, dict):
                issues.append(_issue("DIALOGUE_TURN_INVALID", "turn must be an object", turn_ref))
                continue
            for key in (
                "line_id",
                "speaker",
                "addressee",
                "dialogue_zh",
                "subtitle_zh",
                "dialogue_ja",
                "emotion",
                "subtext",
                "actions",
                "gaze",
                "props",
                "state_delta",
                "source_evidence",
            ):
                if key not in turn:
                    issues.append(_issue("DIALOGUE_FIELD_REQUIRED", f"{key} is required", turn_ref))
            dialogue_texts.update(
                re.sub(r"\s+", "", _text(turn.get(key)))
                for key in ("dialogue_zh", "subtitle_zh", "dialogue_ja")
                if _text(turn.get(key))
            )
            try:
                dialogue_duration += max(0.0, float(turn.get("duration_sec") or 0))
            except (TypeError, ValueError):
                issues.append(_issue("DIALOGUE_DURATION_INVALID", "invalid duration", turn_ref))
            if strict and mode == "dialogue_drama":
                _check_evidence(turn.get("source_evidence"), turn_ref, issues)
                if _pending(turn.get("speaker")) or _pending(turn.get("addressee")):
                    issues.append(
                        _issue("DIALOGUE_PARTICIPANT_REQUIRED", "participants unresolved", turn_ref)
                    )
                if (
                    _text(turn.get("translation_status")) != "ready"
                    or not _text(turn.get("dialogue_ja"))
                    or not _text(turn.get("subtitle_zh"))
                ):
                    issues.append(
                        _issue("DIALOGUE_TRANSLATION_PENDING", "translation not ready", turn_ref)
                    )
                if _text(turn.get("review_status")) not in APPROVED:
                    issues.append(_issue("DIALOGUE_REVIEW_REQUIRED", "turn not reviewed", turn_ref))

    narration_duration = 0.0
    gaps = _gaps(screenplay)
    for gap_ref, gap in gaps:
        try:
            narration_duration += max(0.0, float(gap.get("duration_sec") or 0))
        except (TypeError, ValueError):
            issues.append(_issue("NARRATION_DURATION_INVALID", "invalid duration", gap_ref))
        if strict and mode == "dialogue_drama":
            reason = _text(gap.get("narration_reason"))
            narration = re.sub(r"\s+", "", _text(gap.get("text_zh")))
            visual = re.sub(r"\s+", "", _text(gap.get("visual_information")))
            if reason not in NARRATION_REASONS:
                issues.append(_issue("NARRATION_REASON_REQUIRED", "invalid reason", gap_ref))
            if not _text(gap.get("uncovered_information")):
                issues.append(
                    _issue(
                        "NARRATION_INFORMATION_GAP_REQUIRED",
                        "uncovered information is required",
                        gap_ref,
                    )
                )
            if (
                gap.get("duplicates_dialogue_or_visual") is True
                or (narration and narration in dialogue_texts)
                or (narration and visual and narration == visual)
            ):
                issues.append(
                    _issue("NARRATION_DUPLICATES_STORY", "narration duplicates story", gap_ref)
                )
            _check_evidence(gap.get("source_evidence"), gap_ref, issues)
            if _text(gap.get("review_status")) not in APPROVED:
                issues.append(_issue("NARRATION_REVIEW_REQUIRED", "gap not reviewed", gap_ref))

    total_voice = dialogue_duration + narration_duration
    ratio = narration_duration / total_voice if total_voice else 0.0
    if strict and mode == "dialogue_drama" and ratio > NARRATION_LIMIT:
        issues.append(
            _issue(
                "NARRATION_BUDGET_EXCEEDED",
                f"narration ratio {ratio:.1%} exceeds 15%",
                "narration_gaps",
            )
        )
    return {
        "ok": not issues,
        "issues": issues,
        "metrics": {
            "scenes": len(scenes),
            "dialogue_turns": turn_count,
            "narration_gaps": len(gaps),
            "dialogue_duration_sec": round(dialogue_duration, 3),
            "narration_duration_sec": round(narration_duration, 3),
            "narration_ratio": round(ratio, 4),
            "candidate_only": _text(screenplay.get("status")) == "candidate_only",
        },
    }
