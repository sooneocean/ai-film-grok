#!/usr/bin/env python3
"""Dramatic meaning gates: every shot, motion, and dialogue must carry story purpose.

Temple-AV director bar — machine-checkable layer only:
  1) shot world-change / dramatic function (not aesthetic emptiness)
  2) motion answers the beat (not camera micro-filler alone on drive beats)
  3) spoken lines carry speaker + text + purpose (subtext / emotion / narrative_purpose)
  4) ordered shots stack through director_intent.emotional_arc (coverage + non-flat)

See references/lessons-2026-07-20-meaningful-motion.md and hard-defaults (dramatic meaning).
"""

from __future__ import annotations

from typing import Any

from continuity import (
    CODE_BEAT_SEMANTICS_MISS,
    CODE_MOTION_NO_MEANING,
    CODE_VISIBLE_CHANGE_MISSING,
    lint_meaningful_motion,
)

# Stable issue codes (do not rename lightly — agents, preflight, tests depend on them)
CODE_SHOT_MEANING_EMPTY = "SHOT_MEANING_EMPTY"
CODE_DIALOGUE_SPEAKER_MISSING = "DIALOGUE_SPEAKER_MISSING"
CODE_DIALOGUE_TEXT_EMPTY = "DIALOGUE_TEXT_EMPTY"
CODE_DIALOGUE_PURPOSE_EMPTY = "DIALOGUE_PURPOSE_EMPTY"
CODE_ARC_STACK_FLAT = "ARC_STACK_FLAT"
CODE_ARC_NODE_ORPHAN = "ARC_NODE_ORPHAN"
CODE_ARC_STACK_NO_MAPPING = "ARC_STACK_NO_MAPPING"

_PLACEHOLDERS = frozenset(
    {
        "",
        "todo",
        "tbd",
        "n/a",
        "na",
        "none",
        "null",
        "待定",
        "待填写",
        "待补",
        "needs_authoring",
        "placeholder",
        "to be filled",
        "...",
        "…",
    }
)

_STORY_DRIVE_FUNCTIONS = frozenset(
    {"hook", "approach", "sensory", "reaction", "action", "afterglow"}
)

_HEAT_PHASE_FRAC: dict[str, float] = {
    "setup": 0.0,
    "approach": 0.25,
    "act": 0.55,
    "climax": 0.8,
    "afterglow": 1.0,
}
_DF_FRAC: dict[str, float] = {
    "hook": 0.0,
    "approach": 0.2,
    "sensory": 0.4,
    "reaction": 0.5,
    "action": 0.7,
    "afterglow": 0.95,
    "bridge": 0.35,
}


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _PLACEHOLDERS
    return False


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _norm(value: object) -> str:
    return _text(value).lower()


def _shots_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict):
                out.append(shot)
    return out


def _issue(
    code: str,
    message: str,
    *,
    shot_ids: list[str] | None = None,
    severity: str = "error",
    ref: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "shot_ids": shot_ids or [],
    }
    if ref:
        item["ref"] = ref
    return item


def _dsl(shot: dict[str, Any]) -> dict[str, Any]:
    raw = shot.get("dsl")
    return raw if isinstance(raw, dict) else {}


def _dramatic_function(shot: dict[str, Any]) -> str:
    return _norm(shot.get("dramatic_function") or _dsl(shot).get("dramatic_function"))


def _world_change_blob(shot: dict[str, Any]) -> str:
    dsl = _dsl(shot)
    parts = [
        shot.get("visible_change"),
        shot.get("story_beat"),
        shot.get("performance_delta"),
        dsl.get("visible_change"),
        dsl.get("story_beat"),
        dsl.get("performance_delta"),
    ]
    return " ".join(_text(p) for p in parts if not _is_blank(p)).strip()


def lint_shot_meaning(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Every authored story shot needs dramatic_function + checkable world-change.

    Codes: SHOT_MEANING_EMPTY
    """
    issues: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or f"shot{i + 1}")
        role = _norm(shot.get("shot_role") or "hero")
        fn = _dramatic_function(shot)
        if role in {"env", "insert"} and fn in {"", "bridge"}:
            continue
        if not fn:
            issues.append(
                _issue(
                    CODE_SHOT_MEANING_EMPTY,
                    f"{sid}: missing dramatic_function — every shot needs a story job "
                    "(hook|approach|sensory|reaction|action|afterglow|bridge)",
                    shot_ids=[sid],
                    ref=f"{sid}.dramatic_function",
                )
            )
            continue
        world = _world_change_blob(shot)
        if fn in _STORY_DRIVE_FUNCTIONS and not world:
            issues.append(
                _issue(
                    CODE_SHOT_MEANING_EMPTY,
                    f"{sid} beat={fn}: aesthetic shell without story meaning — "
                    "author dsl.visible_change (in-world A→B) or dsl.story_beat "
                    "(one-line dramatic job) or performance_delta",
                    shot_ids=[sid],
                    ref=f"{sid}.dsl.visible_change",
                )
            )
    codes = sorted({str(i["code"]) for i in issues})
    return {
        "ok": not issues,
        "kind": "shot-meaning",
        "issues": issues,
        "codes": codes,
        "error_count": len(issues),
        "warning_count": 0,
        "blocking": codes,
    }


def lint_motion_purpose(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Motion must serve the beat — wraps meaningful-motion as a purpose gate.

    Codes: MOTION_NO_MEANING, BEAT_SEMANTICS_MISS, VISIBLE_CHANGE_MISSING
    """
    report = lint_meaningful_motion(shots)
    issues: list[dict[str, Any]] = []
    for item in report.get("issues") or []:
        if not isinstance(item, dict):
            continue
        issues.append({**item, "severity": "error"})
    codes = sorted({str(i["code"]) for i in issues})
    return {
        "ok": not issues,
        "kind": "motion-purpose",
        "issues": issues,
        "codes": codes,
        "error_count": len(issues),
        "warning_count": 0,
        "blocking": codes,
        "source": "continuity.lint_meaningful_motion",
    }


def _purpose_fields(line: dict[str, Any]) -> str:
    chunks = [
        line.get("subtext"),
        line.get("emotion"),
        line.get("narrative_purpose"),
        line.get("purpose"),
        line.get("delivery_note"),
        line.get("intent"),
    ]
    return " ".join(_text(c) for c in chunks if not _is_blank(c)).strip()


def _iter_spoken_lines(shot: dict[str, Any], shot_id: str) -> list[dict[str, Any]]:
    """Collect on/off-camera spoken lines from common film-spec shapes."""
    lines: list[dict[str, Any]] = []
    voices = shot.get("voices")
    if isinstance(voices, list):
        for idx, voice in enumerate(voices):
            if not isinstance(voice, dict):
                continue
            line_type = _norm(voice.get("line_type") or "dialogue")
            spoken = _text(voice.get("spoken_text") or voice.get("text"))
            if line_type in {"sfx", "ambience", "music", "bed"}:
                continue
            if not spoken:
                continue
            lines.append(
                {
                    "line_id": str(voice.get("line_id") or f"{shot_id}.voices[{idx}]"),
                    "speaker": voice.get("speaker") or voice.get("character"),
                    "spoken_text": spoken,
                    "subtext": voice.get("subtext"),
                    "emotion": voice.get("emotion"),
                    "narrative_purpose": voice.get("narrative_purpose") or voice.get("purpose"),
                    "delivery_note": voice.get("delivery_note") or voice.get("delivery"),
                    "intent": voice.get("intent"),
                }
            )

    dialogue = _text(shot.get("dialogue") or shot.get("dialogue_ja") or shot.get("dialogue_zh"))
    if dialogue:
        perf = (
            shot.get("performance_state") if isinstance(shot.get("performance_state"), dict) else {}
        )
        lines.append(
            {
                "line_id": str(shot.get("dialogue_line_id") or f"{shot_id}.dialogue"),
                "speaker": shot.get("speaker") or shot.get("dialogue_speaker"),
                "spoken_text": dialogue,
                "subtext": perf.get("subtext") or shot.get("subtext") or _dsl(shot).get("subtext"),
                "emotion": perf.get("emotion") or shot.get("emotion"),
                "narrative_purpose": shot.get("narrative_purpose") or shot.get("dialogue_purpose"),
                "delivery_note": shot.get("delivery_note"),
                "intent": shot.get("intent"),
            }
        )

    ledger = shot.get("dialogue_ledger") or shot.get("dialogue_lines")
    if isinstance(ledger, list):
        for idx, entry in enumerate(ledger):
            if not isinstance(entry, dict):
                continue
            spoken = _text(entry.get("text") or entry.get("spoken_text") or entry.get("line"))
            if not spoken:
                continue
            lines.append(
                {
                    "line_id": str(entry.get("line_id") or f"{shot_id}.ledger[{idx}]"),
                    "speaker": entry.get("speaker") or entry.get("character"),
                    "spoken_text": spoken,
                    "subtext": entry.get("subtext"),
                    "emotion": entry.get("emotion"),
                    "narrative_purpose": entry.get("narrative_purpose")
                    or entry.get("purpose")
                    or entry.get("beat_ref"),
                    "delivery_note": entry.get("delivery_note"),
                    "intent": entry.get("intent"),
                }
            )

    contracts = shot.get("dialogue_contracts")
    if isinstance(contracts, list):
        for c_idx, contract in enumerate(contracts):
            if not isinstance(contract, dict):
                continue
            for l_idx, line in enumerate(contract.get("lines") or []):
                if not isinstance(line, dict):
                    continue
                spoken = _text(line.get("text") or line.get("spoken_text"))
                if not spoken:
                    continue
                lines.append(
                    {
                        "line_id": str(
                            line.get("line_id") or f"{shot_id}.contract[{c_idx}].lines[{l_idx}]"
                        ),
                        "speaker": line.get("speaker") or contract.get("speaker"),
                        "spoken_text": spoken,
                        "subtext": line.get("subtext"),
                        "emotion": line.get("emotion"),
                        "narrative_purpose": line.get("narrative_purpose") or line.get("purpose"),
                        "delivery_note": line.get("delivery") or line.get("delivery_note"),
                        "intent": line.get("intent"),
                    }
                )
    return lines


def _iter_ledger_from_graph(graph: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(graph, dict):
        return []
    ledger = graph.get("dialogue_ledger") or graph.get("dialogue_lines")
    if not isinstance(ledger, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(ledger):
        if not isinstance(entry, dict):
            continue
        spoken = _text(entry.get("text") or entry.get("spoken_text") or entry.get("line"))
        if not spoken:
            continue
        out.append(
            {
                "line_id": str(entry.get("line_id") or f"graph.ledger[{idx}]"),
                "speaker": entry.get("speaker") or entry.get("character"),
                "spoken_text": spoken,
                "subtext": entry.get("subtext"),
                "emotion": entry.get("emotion"),
                "narrative_purpose": entry.get("narrative_purpose")
                or entry.get("purpose")
                or entry.get("beat_ref"),
                "delivery_note": entry.get("delivery_note"),
                "intent": entry.get("intent"),
                "shot_ref": entry.get("shot_ref") or entry.get("shot_id"),
            }
        )
    return out


def lint_dialogue_purpose(
    shots: list[dict[str, Any]],
    *,
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every spoken line needs speaker + non-placeholder text + purpose signal.

    Purpose = subtext and/or emotion / narrative_purpose / delivery intent.
    Codes: DIALOGUE_SPEAKER_MISSING, DIALOGUE_TEXT_EMPTY, DIALOGUE_PURPOSE_EMPTY
    """
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or f"shot{i + 1}")
        for line in _iter_spoken_lines(shot, sid):
            lid = str(line.get("line_id") or "")
            if lid in seen:
                continue
            seen.add(lid)
            speaker = _text(line.get("speaker"))
            spoken = _text(line.get("spoken_text"))
            purpose = _purpose_fields(line)
            sids = [sid]
            if _is_blank(spoken):
                issues.append(
                    _issue(
                        CODE_DIALOGUE_TEXT_EMPTY,
                        f"{lid}: spoken line text is empty/placeholder",
                        shot_ids=sids,
                        ref=lid,
                    )
                )
                continue
            if _is_blank(speaker):
                issues.append(
                    _issue(
                        CODE_DIALOGUE_SPEAKER_MISSING,
                        f"{lid}: spoken line missing speaker — who owns this line?",
                        shot_ids=sids,
                        ref=lid,
                    )
                )
            if _is_blank(purpose):
                issues.append(
                    _issue(
                        CODE_DIALOGUE_PURPOSE_EMPTY,
                        f"{lid}: line is pure filler without purpose — "
                        "author subtext and/or emotion / narrative_purpose "
                        "(what the line does to the emotional stack)",
                        shot_ids=sids,
                        ref=lid,
                    )
                )

    for line in _iter_ledger_from_graph(graph):
        lid = str(line.get("line_id") or "")
        if lid in seen:
            continue
        seen.add(lid)
        speaker = _text(line.get("speaker"))
        spoken = _text(line.get("spoken_text"))
        purpose = _purpose_fields(line)
        sids = [str(line.get("shot_ref") or "")]
        sids = [s for s in sids if s]
        if _is_blank(spoken):
            issues.append(
                _issue(
                    CODE_DIALOGUE_TEXT_EMPTY,
                    f"{lid}: ledger line text is empty/placeholder",
                    shot_ids=sids,
                    ref=lid,
                )
            )
            continue
        if _is_blank(speaker):
            issues.append(
                _issue(
                    CODE_DIALOGUE_SPEAKER_MISSING,
                    f"{lid}: ledger line missing speaker",
                    shot_ids=sids,
                    ref=lid,
                )
            )
        if _is_blank(purpose):
            issues.append(
                _issue(
                    CODE_DIALOGUE_PURPOSE_EMPTY,
                    f"{lid}: ledger line lacks purpose (subtext/emotion/narrative_purpose)",
                    shot_ids=sids,
                    ref=lid,
                )
            )

    codes = sorted({str(i["code"]) for i in issues})
    return {
        "ok": not issues,
        "kind": "dialogue-purpose",
        "issues": issues,
        "codes": codes,
        "error_count": len(issues),
        "warning_count": 0,
        "blocking": codes,
        "checked_lines": len(seen),
    }


def _arc_labels(spec: dict[str, Any]) -> list[str]:
    intent = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    raw = intent.get("emotional_arc")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _emotion_blob(shot: dict[str, Any]) -> str:
    dsl = _dsl(shot)
    perf = shot.get("performance_state") if isinstance(shot.get("performance_state"), dict) else {}
    emotion = shot.get("emotion")
    if isinstance(emotion, dict):
        emotion = emotion.get("primary") or emotion.get("label") or emotion.get("name")
    dsl_emotion = dsl.get("emotion")
    if isinstance(dsl_emotion, dict):
        dsl_emotion = (
            dsl_emotion.get("primary") or dsl_emotion.get("label") or dsl_emotion.get("name")
        )
    parts = [
        shot.get("arc_node"),
        shot.get("emotional_arc_node"),
        shot.get("emotion_label"),
        shot.get("emotional_beat"),
        dsl.get("arc_node"),
        dsl.get("emotional_arc_node"),
        emotion,
        dsl_emotion,
        perf.get("emotion"),
        shot.get("story_beat"),
        dsl.get("story_beat"),
        dsl.get("subtext"),
        shot.get("subtext"),
        shot.get("title"),
        shot.get("nar"),
        dsl.get("visible_change"),
        shot.get("visible_change"),
    ]
    return " ".join(_text(p) for p in parts if not _is_blank(p))


def resolve_shot_arc_index(shot: dict[str, Any], arc: list[str]) -> int | None:
    """Map a shot onto emotional_arc index, or None if unmapped.

    Priority: explicit arc_node → label substring in emotion/story fields →
    heat_phase / dramatic_function positional frac.
    """
    if not arc:
        return None
    dsl = _dsl(shot)
    explicit = _text(
        shot.get("arc_node")
        or shot.get("emotional_arc_node")
        or shot.get("emotion_label")
        or shot.get("emotional_beat")
        or dsl.get("arc_node")
        or dsl.get("emotional_arc_node")
    )
    if explicit:
        el = explicit.lower()
        for i, label in enumerate(arc):
            ll = label.lower()
            if el == ll or el in ll or ll in el:
                return i

    blob = _emotion_blob(shot).lower()
    if blob:
        ranked = sorted(enumerate(arc), key=lambda pair: len(pair[1]), reverse=True)
        for i, label in ranked:
            ll = label.lower()
            if ll and ll in blob:
                return i

    heat = _norm(shot.get("heat_phase") or dsl.get("heat_phase"))
    if heat in _HEAT_PHASE_FRAC:
        frac = _HEAT_PHASE_FRAC[heat]
        return min(len(arc) - 1, max(0, int(round(frac * (len(arc) - 1)))))

    fn = _dramatic_function(shot)
    if fn in _DF_FRAC:
        frac = _DF_FRAC[fn]
        return min(len(arc) - 1, max(0, int(round(frac * (len(arc) - 1)))))

    return None


def lint_emotional_arc_stack(
    shots: list[dict[str, Any]],
    emotional_arc: list[str] | None = None,
    *,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shots must progress through emotional_arc — coverage + non-flat stack.

    Codes: ARC_STACK_FLAT, ARC_NODE_ORPHAN, ARC_STACK_NO_MAPPING
    Skips when arc is absent or shorter than 3 (director_intent owns that floor).
    """
    if emotional_arc is None and isinstance(spec, dict):
        emotional_arc = _arc_labels(spec)
    arc = [a.strip() for a in (emotional_arc or []) if isinstance(a, str) and a.strip()]
    if len(arc) < 3:
        return {
            "ok": True,
            "kind": "emotional-arc-stack",
            "issues": [],
            "codes": [],
            "error_count": 0,
            "warning_count": 0,
            "blocking": [],
            "skipped": True,
            "reason": "emotional_arc missing or <3 nodes",
            "assignments": [],
        }

    story_shots = [
        s
        for s in shots
        if isinstance(s, dict) and _norm(s.get("shot_role") or "hero") not in {"env", "insert"}
    ]
    if not story_shots:
        story_shots = [s for s in shots if isinstance(s, dict)]

    assignments: list[dict[str, Any]] = []
    indices: list[int] = []
    for i, shot in enumerate(story_shots):
        sid = str(shot.get("id") or f"shot{i + 1}")
        idx = resolve_shot_arc_index(shot, arc)
        assignments.append(
            {
                "shot_id": sid,
                "arc_index": idx,
                "arc_label": arc[idx] if idx is not None else None,
            }
        )
        if idx is not None:
            indices.append(idx)

    issues: list[dict[str, Any]] = []
    if not indices:
        issues.append(
            _issue(
                CODE_ARC_STACK_NO_MAPPING,
                "emotional_arc is authored but no shot maps onto it — set arc_node / "
                "emotion matching an arc label, or heat_phase / dramatic_function for "
                "positional stack",
                shot_ids=[str(a["shot_id"]) for a in assignments],
            )
        )
    else:
        unique = set(indices)
        if len(story_shots) >= 2 and len(unique) < 2:
            issues.append(
                _issue(
                    CODE_ARC_STACK_FLAT,
                    "emotional stack is flat — all mapped shots sit on one arc node "
                    f"({arc[indices[0]]!r}); progress the ordered shot list through "
                    "the arc so feeling accumulates",
                    shot_ids=[str(a["shot_id"]) for a in assignments],
                )
            )

        if len(story_shots) >= len(arc):
            orphans = [arc[i] for i in range(len(arc)) if i not in unique]
            if orphans:
                issues.append(
                    _issue(
                        CODE_ARC_NODE_ORPHAN,
                        "arc nodes never visited by any shot: "
                        + ", ".join(repr(o) for o in orphans)
                        + " — assign arc_node or restage coverage so the stack completes",
                        shot_ids=[str(a["shot_id"]) for a in assignments],
                    )
                )
        else:
            if len(indices) >= 2 and max(indices) == min(indices):
                if not any(i["code"] == CODE_ARC_STACK_FLAT for i in issues):
                    issues.append(
                        _issue(
                            CODE_ARC_STACK_FLAT,
                            "emotional stack does not progress — mapped shots freeze "
                            f"on {arc[indices[0]]!r}",
                            shot_ids=[str(a["shot_id"]) for a in assignments],
                        )
                    )

    codes = sorted({str(i["code"]) for i in issues})
    return {
        "ok": not issues,
        "kind": "emotional-arc-stack",
        "issues": issues,
        "codes": codes,
        "error_count": len(issues),
        "warning_count": 0,
        "blocking": codes,
        "arc": arc,
        "assignments": assignments,
        "covered_indices": sorted(set(indices)),
    }


def meaning_gate_enabled(spec: dict[str, Any] | None) -> bool:
    """Whether dramatic meaning fails closed on validate/preflight.

    Explicit dramatic_meaning_strict wins.
    Default-on for heat_scale=max, premium_vertical, or adult_max_iron profiles.
    write-spec still fail-closes via cinematic_audit (always applies meaning issues).
    """
    if not isinstance(spec, dict):
        return False
    flag = spec.get("dramatic_meaning_strict")
    if flag is True:
        return True
    if flag is False:
        return False
    heat = _norm(spec.get("heat_scale"))
    if heat == "max":
        return True
    qt = _norm(spec.get("quality_target"))
    if qt in {"premium_vertical", "premium", "max"}:
        return True
    if spec.get("adult_max_iron") is True:
        return True
    return False


def lint_dramatic_meaning(
    spec: dict[str, Any] | None = None,
    *,
    shots: list[dict[str, Any]] | None = None,
    graph: dict[str, Any] | None = None,
    emotional_arc: list[str] | None = None,
) -> dict[str, Any]:
    """Composite gate: shot meaning + motion purpose + dialogue purpose + arc stack."""
    source = spec if isinstance(spec, dict) else {}
    shot_list = shots if shots is not None else _shots_from_spec(source)
    parts = {
        "shot_meaning": lint_shot_meaning(shot_list),
        "motion_purpose": lint_motion_purpose(shot_list),
        "dialogue_purpose": lint_dialogue_purpose(shot_list, graph=graph),
        "emotional_arc_stack": lint_emotional_arc_stack(
            shot_list, emotional_arc=emotional_arc, spec=source
        ),
    }
    issues: list[dict[str, Any]] = []
    codes: set[str] = set()
    for part in parts.values():
        for item in part.get("issues") or []:
            if isinstance(item, dict):
                issues.append(item)
                codes.add(str(item.get("code") or ""))
    codes.discard("")
    enabled = meaning_gate_enabled(source)
    return {
        "ok": not issues,
        "kind": "dramatic-meaning",
        "enabled": enabled,
        "issues": issues,
        "codes": sorted(codes),
        "error_count": len(issues),
        "warning_count": 0,
        "blocking": sorted(codes) if enabled else [],
        "parts": parts,
        "checked": {
            "shots": len(shot_list),
            "dialogue_lines": int(parts["dialogue_purpose"].get("checked_lines") or 0),
            "arc_nodes": len(parts["emotional_arc_stack"].get("arc") or []),
        },
        "motion_codes": [
            CODE_MOTION_NO_MEANING,
            CODE_BEAT_SEMANTICS_MISS,
            CODE_VISIBLE_CHANGE_MISSING,
        ],
        "note": (
            "Every shot needs dramatic_function + world-change; motion must answer "
            "the beat; dialogue needs purpose; shots must stack through emotional_arc. "
            "Fail-closed when dramatic_meaning_strict is on (default for production)."
        ),
    }
