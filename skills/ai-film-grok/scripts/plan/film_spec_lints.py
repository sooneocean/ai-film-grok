#!/usr/bin/env python3
"""Film-spec validation leaf (M1 peel · 2026-08-06).

Public entry remains ``film_spec.validate_film_spec`` via re-export.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from plan.film_spec_constants import *  # noqa: F403
except ImportError:  # pragma: no cover
    from film_spec_constants import *  # type: ignore  # noqa: F403
from film_spec_profile import (  # noqa: F401
    DEFAULT_H3_CONFIG,
    FRW_I2V_FRW_ONLY_LIFEBOAT,
    I2V_PROVIDERS,
    default_frw_video_model,
    default_i2v_provider,
    frw_i2v_fallback_chain,
    resolve_h3_config,
    resolve_i2v_profile,
)

__all__ = [
    "FilmSpecError","iter_film_spec_shots","_required_text","estimate_nar_vo_sec",
    "validate_nar_budget","_validate_dialogue_drama_shot","validate_director_intent",
    "validate_dramatic_function","_PERFORMANCE_PLACEHOLDERS","PERFORMANCE_FIELDS",
    "_is_unauthored","lint_performance","DIRECTOR_BOARD_FIELDS","lint_director_board",
    "zero_narration_gate",
]
class FilmSpecError(ValueError):
    pass


def iter_film_spec_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return shots from the canonical nested schema or the legacy flat projection."""
    flat = spec.get("shots")
    if isinstance(flat, list):
        return [shot for shot in flat if isinstance(shot, dict)]
    scenes = spec.get("scenes")
    if not isinstance(scenes, list):
        return []
    return [
        shot
        for scene in scenes
        if isinstance(scene, dict)
        for shot in (scene.get("shots") if isinstance(scene.get("shots"), list) else [])
        if isinstance(shot, dict)
    ]


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FilmSpecError(f"film-spec requires non-empty {field}")
    return value.strip()


def estimate_nar_vo_sec(nar: str) -> float:
    """Estimate VO duration in seconds from narration text length."""
    text = (nar or "").strip()
    if not text:
        return 0.0
    return max(1.0, round(len(text) / NAR_CHARS_PER_SEC, 2))


def validate_nar_budget(nar: object, *, field: str) -> str:
    """Require non-empty nar and enforce hard max length (vo_budget gate)."""
    text = _required_text(nar, field=field)
    n = len(text)
    if n > MAX_NAR_CHARS:
        raise FilmSpecError(
            f"{field} vo_budget exceeded: {n} chars > max {MAX_NAR_CHARS} "
            f"(recommended ≤{RECOMMENDED_NAR_CHARS}; split the shot or cut sensory clauses)"
        )
    return text


def _validate_dialogue_drama_shot(
    shot: dict[str, Any], *, shot_id: str, narration_gap_strict: bool = False
) -> None:
    """Require an explicit, single-purpose audio contract for dialogue-first shots."""
    screen_mode = str(shot.get("screen_mode") or "").strip().lower()
    valid_modes = {"on_camera", "off_camera", "reaction", "action_cover", "silence"}
    if screen_mode not in valid_modes:
        raise FilmSpecError(f"{shot_id}.screen_mode must be one of {sorted(valid_modes)}")
    cues = shot.get("audio_cues")
    if not isinstance(cues, list) or not cues:
        raise FilmSpecError(f"{shot_id}: dialogue_drama requires explicit audio_cues")
    voices = [cue for cue in cues if isinstance(cue, dict) and cue.get("kind") == "voice"]
    if screen_mode == "on_camera":
        if len(voices) != 1:
            raise FilmSpecError(f"{shot_id}: on_camera dialogue requires exactly one voice cue")
        voice = voices[0]
        if voice.get("line_type") != "dialogue" or not str(voice.get("spoken_text") or "").strip():
            raise FilmSpecError(
                f"{shot_id}: on_camera voice must be a dialogue cue with spoken_text"
            )
        voice_lang = str(voice.get("language") or "zh").lower()
        if voice_lang in {"ja", "jp", "japanese"}:
            raise FilmSpecError(
                f"{shot_id}: Japanese dialogue is retired; set language=zh and Chinese spoken_text"
            )
        if voice_lang not in {"", "zh", "cn", "chinese", "zh-cn", "zh_cn"}:
            raise FilmSpecError(
                f"{shot_id}: character dialogue voice language must be zh (Chinese-only product)"
            )
        spoken = str(voice.get("spoken_text") or "").strip()
        caption = str(shot.get("caption_text") or spoken).strip()
        if not re.search(r"[\u4e00-\u9fff]", spoken + caption):
            raise FilmSpecError(
                f"{shot_id}: Chinese dialogue requires Han characters in spoken_text/caption_text"
            )
        if not str(shot.get("caption_text") or "").strip():
            raise FilmSpecError(
                f"{shot_id}: dialogue requires Chinese caption_text (HyperFrames subtitle owner)"
            )
        if not str(shot.get("dialogue_line_id") or "").strip():
            raise FilmSpecError(f"{shot_id}: on_camera dialogue requires dialogue_line_id")
        if not str(shot.get("performance_state_id") or "").strip():
            raise FilmSpecError(f"{shot_id}: on_camera dialogue requires performance_state_id")
        if shot.get("lipsync_required") is not True:
            raise FilmSpecError(f"{shot_id}: on_camera dialogue requires lipsync_required=true")
        if not bool(shot.get("speaker_on_camera")) or shot.get("lipsync") is not True:
            raise FilmSpecError(
                f"{shot_id}: on_camera dialogue requires speaker_on_camera and lipsync"
            )
        if str(voice.get("speaker") or "") != str(shot.get("speaker") or ""):
            raise FilmSpecError(f"{shot_id}: dialogue speaker must match voice cue speaker")
        if len(str(voice.get("spoken_text") or "").strip()) > MAX_ON_CAMERA_DIALOGUE_CHARS:
            raise FilmSpecError(
                f"{shot_id}: on_camera dialogue exceeds {MAX_ON_CAMERA_DIALOGUE_CHARS} chars; "
                "split it with reaction/action coverage"
            )
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
        shot_size = str(camera.get("shot_size") or shot.get("shot_size") or "").lower().strip()
        if shot_size not in ON_CAMERA_SHOT_SIZES:
            raise FilmSpecError(
                f"{shot_id}: on_camera dialogue requires near framing "
                f"{sorted(ON_CAMERA_SHOT_SIZES)}"
            )
        head_angle = str(
            (shot.get("performance_state") or {}).get("head_angle")
            if isinstance(shot.get("performance_state"), dict)
            else ""
        ).lower()
        if head_angle and not any(
            token in head_angle for token in ("front", "three-quarter", "微侧", "正脸")
        ):
            raise FilmSpecError(
                f"{shot_id}: on_camera dialogue requires front or three-quarter face"
            )
    elif screen_mode == "action_cover" and voices and voices[0].get("line_type") == "narration":
        if len(voices) != 1:
            raise FilmSpecError(
                f"{shot_id}: {screen_mode} narration requires one narration voice cue"
            )
        if not str(shot.get("narration_reason") or "").strip():
            raise FilmSpecError(f"{shot_id}: {screen_mode} narration requires narration_reason")
        if narration_gap_strict:
            gap = shot.get("narration_gap")
            if not isinstance(gap, dict):
                raise FilmSpecError(
                    f"{shot_id}: {screen_mode} narration requires narration_gap evidence"
                )
            allowed = {
                "time_jump",
                "location_context",
                "scene_establish",
                "chapter_transition",
                "offscreen_fact",
                "inner_context",
                "narrative_gap",
                "ending_afterglow",
            }
            if not str(gap.get("gap_id") or "").strip():
                raise FilmSpecError(f"{shot_id}: narration_gap.gap_id is required")
            if str(gap.get("reason") or "") not in allowed:
                raise FilmSpecError(
                    f"{shot_id}: narration_gap.reason must be one of {sorted(allowed)}"
                )
            uncovered = str(gap.get("uncovered_information") or "").strip()
            if not uncovered:
                raise FilmSpecError(f"{shot_id}: narration_gap.uncovered_information is required")
            voice_text = str(voices[0].get("spoken_text") or "").strip()
            if (
                str(gap.get("reason") or "") == "narrative_gap"
                and float(voices[0].get("duration_sec") or 0) <= 1.2
            ):
                raise FilmSpecError(
                    f"{shot_id}: narrative_gap narration requires more than 1.2 seconds"
                )
            visible = " ".join(
                str(value or "").strip()
                for value in (
                    shot.get("must_show"),
                    shot.get("visible_change"),
                    (shot.get("dsl") or {}).get("action")
                    if isinstance(shot.get("dsl"), dict)
                    else "",
                )
                if str(value or "").strip()
            )
            compact_voice = re.sub(r"[\W_]+", "", voice_text)
            compact_visible = re.sub(r"[\W_]+", "", visible)
            if (
                compact_voice
                and compact_visible
                and (compact_voice in compact_visible or compact_visible in compact_voice)
            ):
                raise FilmSpecError(
                    f"{shot_id}: narration duplicates visible information; use silence/ambience"
                )
    elif voices and screen_mode != "silence":
        if len(voices) != 1 or voices[0].get("line_type") != "dialogue":
            raise FilmSpecError(
                f"{shot_id}: {screen_mode} may carry only one continuing dialogue cue"
            )
        if shot.get("lipsync") is True or shot.get("speaker_on_camera") is True:
            raise FilmSpecError(f"{shot_id}: {screen_mode} dialogue must not claim visible lipsync")
    elif voices:
        raise FilmSpecError(f"{shot_id}: silence cannot carry voice")


def validate_director_intent(spec: dict[str, Any]) -> dict[str, Any]:
    """Require director_intent so production cannot start without a stated promise."""
    raw = spec.get("director_intent")
    if not isinstance(raw, dict):
        raise FilmSpecError(
            "film-spec requires director_intent object "
            "(logline, tone, emotional_arc) before write-spec / media-queue"
        )
    logline = _required_text(raw.get("logline"), field="director_intent.logline")
    if len(logline) < MIN_LOGLINE_LEN:
        raise FilmSpecError(
            f"director_intent.logline too short (min {MIN_LOGLINE_LEN} chars) — state the film's promise"
        )
    tone = _required_text(raw.get("tone"), field="director_intent.tone")
    arc = raw.get("emotional_arc")
    if not isinstance(arc, list) or len(arc) < MIN_EMOTIONAL_ARC:
        raise FilmSpecError(
            f"director_intent.emotional_arc must be an array with ≥{MIN_EMOTIONAL_ARC} beat labels"
        )
    cleaned_arc: list[str] = []
    for i, item in enumerate(arc):
        if not isinstance(item, str) or not item.strip():
            raise FilmSpecError(f"director_intent.emotional_arc[{i}] must be non-empty string")
        cleaned_arc.append(item.strip())
    intent: dict[str, Any] = {
        "logline": logline,
        "tone": tone,
        "emotional_arc": cleaned_arc,
    }
    if raw.get("audience") is not None:
        intent["audience"] = _required_text(raw.get("audience"), field="director_intent.audience")
    taboos = raw.get("taboos")
    if taboos is not None:
        if not isinstance(taboos, list):
            raise FilmSpecError("director_intent.taboos must be an array of strings")
        intent["taboos"] = [
            _required_text(t, field=f"director_intent.taboos[{i}]") for i, t in enumerate(taboos)
        ]

    # P0-2: act_structure + pace_chart validation (strict mode)
    act_raw = raw.get("act_structure")
    pace_raw = raw.get("pace_chart")
    act_strict = bool(spec.get("act_structure_strict"))
    pace_strict = bool(spec.get("pace_chart_strict"))

    # act_structure: if present, validate shape + ratio sum
    if isinstance(act_raw, dict):
        act_cleaned: dict[str, Any] = {}
        for act_key in ("setup", "confrontation", "resolution"):
            val = act_raw.get(act_key)
            if val is not None:
                act_cleaned[act_key] = _required_text(val, field=f"act_structure.{act_key}")
        ratios = {}
        for rkey in ("setup_ratio", "confrontation_ratio", "resolution_ratio"):
            rval = act_raw.get(rkey)
            if rval is not None:
                if not isinstance(rval, (int, float)) or rval < 0.05 or rval > 0.70:
                    raise FilmSpecError(f"act_structure.{rkey}={rval} out of range [0.05, 0.70]")
                ratios[rkey] = float(rval)
        # If all three ratios present, they should sum to ~1.0
        if len(ratios) == 3:
            total = sum(ratios.values())
            if abs(total - 1.0) > 0.05:
                raise FilmSpecError(
                    f"act_structure ratios sum={total:.3f}, expected ~1.0 "
                    f"(setup+confrontation+resolution)"
                )
            act_cleaned.update(ratios)
        elif ratios:
            act_cleaned.update(ratios)
        if act_strict:
            missing_acts = [
                key for key in ("setup", "confrontation", "resolution") if not act_cleaned.get(key)
            ]
            if missing_acts:
                raise FilmSpecError(
                    "act_structure_strict: required fields missing: " + ", ".join(missing_acts)
                )
        if act_cleaned:
            intent["act_structure"] = act_cleaned
    elif act_strict:
        raise FilmSpecError(
            "act_structure_strict: act_structure object required when strict mode is enabled"
        )

    # pace_chart: if present, validate structured entries (new format)
    # Also accept legacy string-array format (backward compat)
    if isinstance(pace_raw, list):
        if len(pace_raw) == 0:
            if pace_strict:
                raise FilmSpecError("pace_chart_strict: pace_chart must be non-empty when strict")
        else:
            pace_cleaned: list[Any] = []
            for i, entry in enumerate(pace_raw):
                if isinstance(entry, str):
                    # Legacy string format — accept as-is
                    pace_cleaned.append(entry.strip())
                elif isinstance(entry, dict):
                    label = _required_text(entry.get("label"), field=f"pace_chart[{i}].label")
                    sr = entry.get("start_ratio")
                    er = entry.get("end_ratio")
                    if not isinstance(sr, (int, float)) or not (0 <= sr <= 1):
                        raise FilmSpecError(
                            f"pace_chart[{i}].start_ratio={sr} must be number in [0,1]"
                        )
                    if not isinstance(er, (int, float)) or not (0 <= er <= 1):
                        raise FilmSpecError(
                            f"pace_chart[{i}].end_ratio={er} must be number in [0,1]"
                        )
                    if er <= sr:
                        raise FilmSpecError(f"pace_chart[{i}].end_ratio must be > start_ratio")
                    intensity = entry.get("intensity")
                    if intensity is not None and (
                        not isinstance(intensity, (int, float)) or not (0 <= intensity <= 10)
                    ):
                        raise FilmSpecError(
                            f"pace_chart[{i}].intensity={intensity} must be in [0,10]"
                        )
                    entry_clean: dict[str, Any] = {
                        "label": label,
                        "start_ratio": float(sr),
                        "end_ratio": float(er),
                    }
                    if entry.get("cut_freq"):
                        entry_clean["cut_freq"] = str(entry["cut_freq"])
                    if intensity is not None:
                        entry_clean["intensity"] = float(intensity)
                    pace_cleaned.append(entry_clean)
                else:
                    raise FilmSpecError(
                        f"pace_chart[{i}] must be string or object, got {type(entry).__name__}"
                    )
            if pace_strict and len(pace_cleaned) < 3:
                raise FilmSpecError(f"pace_chart_strict: need ≥3 segments, got {len(pace_cleaned)}")
            if pace_cleaned:
                intent["pace_chart"] = pace_cleaned
    elif pace_strict:
        raise FilmSpecError(
            "pace_chart_strict: pace_chart array required when strict mode is enabled"
        )

    # P0-3: character bible strict — protagonist must have want/need/arc
    char_strict = bool(spec.get("character_bible_strict"))
    for pfield in ("protagonist_want", "protagonist_need", "protagonist_arc"):
        val = raw.get(pfield)
        if val is not None:
            intent[pfield] = _required_text(val, field=f"director_intent.{pfield}")
        elif char_strict:
            raise FilmSpecError(
                f"character_bible_strict: director_intent.{pfield} required when strict mode is enabled"
            )

    spec["director_intent"] = intent
    return intent


def validate_dramatic_function(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FilmSpecError(
            f"{field} is required — one of {sorted(DRAMATIC_FUNCTIONS)} "
            "(shot role in the story spine, not only a pretty frame)"
        )
    fn = value.strip().lower()
    if fn not in DRAMATIC_FUNCTIONS:
        raise FilmSpecError(f"{field} must be one of {sorted(DRAMATIC_FUNCTIONS)}; got {value!r}")
    return fn


# Placeholder strings that never count as authored director intent (mirrors
# narrative_control.PLACEHOLDER_RE so film-spec and drama-graph agree on
# "needs_authoring" semantics).
_PERFORMANCE_PLACEHOLDERS = frozenset(
    {
        "",
        "todo",
        "tbd",
        "needs_authoring",
        "待补",
        "待定",
        "待填写",
    }
)

# Fields that carry character interiority — the "why" behind the motion.
# Absent or placeholder → SHOT_PERFORMANCE_MISSING (warning by default;
# performance_strict=true raises). Aligns film-spec with drama-graph's
# shot-level validation (see narrative_control.validate_narrative_graph).
PERFORMANCE_FIELDS = ("subtext", "playable_action", "body_state")


def _is_unauthored(value: object) -> bool:
    return not isinstance(value, str) or value.strip().lower() in _PERFORMANCE_PLACEHOLDERS


def lint_performance(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Surface shots that have motion but no performance intent.

    I2V can move bodies; subtext is what makes them *act*. This lint is the
    film-spec echo of drama-graph's SHOT_PERFORMANCE_MISSING — it asks, for
    every shot: "we know the camera moves, but what is the character's
    interior change A→B?" Missing on hook/approach/action is a stronger
    signal than on bridge/insert (env beds have no performer).
    """
    issues: list[dict[str, Any]] = []
    for shot in shots:
        sid = str(shot.get("id") or "")
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        fn = str(shot.get("dramatic_function") or "").strip().lower()
        role = str(shot.get("shot_role") or "hero").strip().lower()
        # Env/insert beds have no performer to direct — skip performance lint.
        if role in {"env", "insert"} and fn == "bridge":
            continue
        missing = [f for f in PERFORMANCE_FIELDS if _is_unauthored(dsl.get(f))]
        if not missing:
            continue
        # hook/approach/action carry the story spine — stronger severity.
        spine = fn in {"hook", "approach", "action"}
        issues.append(
            {
                "code": "SHOT_PERFORMANCE_MISSING",
                "severity": "warning",
                "shot_id": sid,
                "fields": missing,
                "dramatic_function": fn,
                "message": (
                    f"{sid} ({fn}) has motion but no performance intent: "
                    f"missing {missing}. I2V moves the body; subtext makes it act. "
                    "Fill dsl.subtext (interiority) / playable_action (actable verb) "
                    "/ body_state (micro-expression)."
                ),
                "spine": spine,
            }
        )
    return {
        "ok": len(issues) == 0,
        "codes": sorted({i["code"] for i in issues}),
        "warning_count": len(issues),
        "issues": issues,
    }


# Director board fields mirrored from narrative_control.DIRECTOR_BOARD_FIELDS
# so the production contract and the canonical graph stay in sync.
DIRECTOR_BOARD_FIELDS = (
    "emotional_turn",
    "audience_question",
    "coverage_strategy",
    "cut_intent",
)


def lint_director_board(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    """Check each scene's director_board is authored, not placeholder.

    The director board is the production-meeting checklist: what turns, what
    question does the audience hold, how do we cover and cut it. A scene
    with a board full of "needs_authoring" has had its shots pre-decided
    without a director's pass — the classic AI-film failure of beautiful
    frames with no governing intent.
    """
    issues: list[dict[str, Any]] = []
    for idx, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        board = scene.get("director_board")
        label = f"scene{idx}"
        if not isinstance(board, dict):
            # No board at all is soft by default (existing films don't have it);
            # scene_strict=true will require it. We report, don't fail.
            issues.append(
                {
                    "code": "DIRECTOR_BOARD_MISSING",
                    "severity": "warning",
                    "scene": label,
                    "message": (
                        f"{label} has no director_board — emotional_turn / "
                        "audience_question / coverage_strategy / cut_intent "
                        "should be authored before bulk."
                    ),
                }
            )
            continue
        for field in DIRECTOR_BOARD_FIELDS:
            if _is_unauthored(board.get(field)):
                issues.append(
                    {
                        "code": "DIRECTOR_BOARD_FIELD_MISSING",
                        "severity": "warning",
                        "scene": label,
                        "field": field,
                        "message": (
                            f"{label}.director_board.{field} is missing or placeholder — "
                            "author it before approving this scene for bulk."
                        ),
                    }
                )
        approval = str(board.get("approval_state") or "draft").strip().lower()
        if approval not in {"draft", "review", "approved"}:
            issues.append(
                {
                    "code": "DIRECTOR_BOARD_APPROVAL_INVALID",
                    "severity": "warning",
                    "scene": label,
                    "message": (
                        f"{label}.director_board.approval_state must be "
                        "draft|review|approved; got {approval!r}"
                    ),
                }
            )
    return {
        "ok": len(issues) == 0,
        "codes": sorted({i["code"] for i in issues}),
        "warning_count": len(issues),
        "issues": issues,
    }


def zero_narration_gate(
    spec: dict[str, Any],
    *,
    shots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure zero-narration IRON gate for dialogue_drama (Delivery Truth · 2.36.4).

    Defaults ``zero_narration_strict=true`` when ``vo_mode=dialogue_drama``.
    Ratio = max(shot-level third-person nar share, voice-cue narration duration share).
    Does not raise — callers raise FilmSpecError with code NAR_BUDGET_VIOLATION.
    """
    if not isinstance(spec, dict):
        return {"ok": True, "checked": False, "reason": "not_a_spec"}
    vo_mode = str(spec.get("vo_mode") or "").strip().lower()
    if vo_mode != "dialogue_drama":
        return {
            "ok": True,
            "checked": False,
            "reason": "not_dialogue_drama",
            "zero_narration_strict": False,
            "ratio": 0.0,
        }
    if "zero_narration_strict" in spec:
        zero_strict = bool(spec.get("zero_narration_strict"))
    else:
        zero_strict = True  # IRON default
    if not zero_strict:
        return {
            "ok": True,
            "checked": True,
            "zero_narration_strict": False,
            "ratio": 0.0,
            "escape": "zero_narration_strict:false",
        }

    if shots is None:
        shots = []
        for scene in spec.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for sh in scene.get("shots") or []:
                if isinstance(sh, dict):
                    shots.append(sh)
        if not shots and isinstance(spec.get("shots"), list):
            shots = [s for s in spec["shots"] if isinstance(s, dict)]

    total = 0
    nar_shots = 0
    dialogue_sec = 0.0
    narration_sec = 0.0
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        total += 1
        cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
        has_dialogue = bool(str(shot.get("spoken_text") or "").strip())
        has_dialogue_voice = any(
            isinstance(c, dict)
            and c.get("kind") == "voice"
            and c.get("line_type") == "dialogue"
            and (str(c.get("spoken_text") or "").strip() or float(c.get("duration_sec") or 0) > 0)
            for c in cues
        )
        has_dialogue = has_dialogue or has_dialogue_voice
        for c in cues:
            if not isinstance(c, dict) or c.get("kind") != "voice":
                continue
            dur = float(c.get("duration_sec") or 0)
            if c.get("line_type") == "dialogue":
                dialogue_sec += dur
            elif c.get("line_type") == "narration":
                narration_sec += dur
        nar = str(shot.get("nar") or "").strip()
        # silent_scene + narration_reason is an explicit gap escape
        if (
            nar
            and not has_dialogue
            and not (
                shot.get("silent_scene") is True and str(shot.get("narration_reason") or "").strip()
            )
        ):
            nar_shots += 1

    shot_ratio = (nar_shots / total) if total else 0.0
    cue_ratio = narration_sec / max(dialogue_sec + narration_sec, 1.0)
    ratio = max(shot_ratio, cue_ratio)
    if ratio > 1e-9:
        return {
            "ok": False,
            "checked": True,
            "zero_narration_strict": True,
            "code": "NAR_BUDGET_VIOLATION",
            "ratio": round(ratio, 4),
            "shot_ratio": round(shot_ratio, 4),
            "cue_ratio": round(cue_ratio, 4),
            "message": (
                f"zero_narration_strict:true but narration_ratio={ratio:.2%}. "
                "Replace third-person nar with character dialogue, prop inserts, or Foley SFX. "
                "Escape: zero_narration_strict:false or silent_scene+narration_reason."
            ),
        }
    return {
        "ok": True,
        "checked": True,
        "zero_narration_strict": True,
        "ratio": 0.0,
        "code": None,
    }
