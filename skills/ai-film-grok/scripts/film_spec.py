#!/usr/bin/env python3
"""Strict film-spec validation shared by control-plane and renderer."""

from __future__ import annotations

from typing import Any

from audio_recipe import (
    AudioRecipeError,
    apply_audio_recipes_to_spec,
    probe_caps_for_root,
)
from content_channels import lint_content_channels
from continuity import (
    lint_continuity,
    lint_frame_chain,
    lint_meaningful_motion,
    lint_transition_styles,
    lint_vo_motion_link,
)
from continuity_chain import (
    is_long_form,
)
from edit_policy import (
    _CRAFT_WHY,
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    apply_coverage_defaults_to_shot,
    apply_heat_phase_defaults,
    apply_wardrobe_continuity,
    edit_crafts_to_intents,
    enforce_continue_hard_joins,
    lint_character_stance,
    lint_heat_arc,
    lint_multi_heroine,
    normalize_edit_craft,
    normalize_heat_scale,
    normalize_transition_intent,
    normalize_transition_sec,
    normalize_transition_styles,
    normalize_xfade_style,
    resolve_heroine_cast_mode,
    suggest_edit_crafts,
    suggest_transition_intents,
    suggest_transition_styles,
    validate_motion,
)
from framing_lint import lint_framing_iron, lint_vertical_safe_area
from rhythm import lint_rhythm
from security_policy import SecurityPolicyError, validate_identifier
from sound_plan import (
    SoundPlanError,
    default_sound_plan_for_film,
    inject_auto_sfx_if_empty,
    inject_sex_sfx_from_shots,
    resolve_sidechain,
    validate_sound_plan,
)

VO_MODES = frozenset({"storyteller", "character", "hybrid"})
TTS_BACKENDS = frozenset({"auto", "minimax", "fish", "voicebox", "edge", "external", "grok"})
# Bulk motion provider profiles (see resolve_i2v_profile):
# - seedance_first: FRW Seedance bulk when account open
# - grok_primary: Seedance unavailable / 403 season — Grok image_to_video bulk
I2V_PROVIDERS = frozenset({"frw", "grok", "auto"})
I2V_PROFILES = frozenset({"seedance_first", "grok_primary"})
# Native resolution for 9:16 shorts — never generate 576 then upscale to 720
DEFAULT_FRW_ASPECT = "9:16"
DEFAULT_FRW_RESOLUTION = "720p"
DEFAULT_FRW_DURATION = "5"
DEFAULT_FRW_FPS = "24"
# LTX preferred pixel size for vertical shorts (probe-validated 2026-07-20)
DEFAULT_LTX_WIDTH = "720"
DEFAULT_LTX_HEIGHT = "1280"
# Explicit last-resort (never default; agent must set frw_video_model deliberately)
FRW_I2V_FRW_ONLY_LIFEBOAT = "legacy-img2video"
# Env / synth layer (no face import): LTX T2V is primary for B-roll beds
# 2026-07-21: ltx-t2v completed on sample key; seedance t2v may 403
DEFAULT_FRW_ENV_MODEL = "ltx-t2v"
# FRW video model keys (frwclaw NEW_VIDEO_TEMPLATES + legacy)
# NEVER default legacy img2video (胃镜室质量坑).
FRW_VIDEO_MODELS = frozenset(
    {
        "seedance-2-fast-i2v",  # FRW bulk when permission open
        "seedance-2-fast-t2v",
        "seedance-2-pro-flf",  # multi-ref / first-last style (pro)
        "seedance-2-pro-t2v",
        "byteplus-seedance-2-i2v",  # alt channel i2v
        "byteplus-seedance-2-flf",
        "byteplus-seedance-2-t2v",
        # LTX family — width/height/duration/fps must be strings; precise 9:16
        "ltx-i2v",
        "ltx-t2v",
        "ltx-flf",
        "ltx-lipsync",
        "legacy-img2video",  # explicit opt-in only — quality floor
        "auto",
    }
)


def resolve_i2v_profile() -> str:
    """Operating profile for hero I2V bulk.

    Env (first wins):
      AIFILM_I2V_PROFILE=grok_primary|seedance_first
      AIFILM_SEEDANCE_AVAILABLE=0|false|no → grok_primary
    Default (2026-07-21 Seedance outage season): grok_primary.
    Restore Seedance bulk: AIFILM_I2V_PROFILE=seedance_first and canary 201.
    """
    from config_loader import get_config

    cfg = get_config()
    raw = cfg.i2v_profile.strip().lower()
    if raw in I2V_PROFILES:
        return raw
    if not cfg.seedance_available:
        return "grok_primary"
    return "seedance_first"


def default_i2v_provider() -> str:
    return "grok" if resolve_i2v_profile() == "grok_primary" else "frw"


def default_frw_video_model() -> str:
    # Keep seedance model id documented for when profile flips back; not used for grok L1
    return "seedance-2-fast-i2v"


def frw_i2v_fallback_chain() -> tuple[str, ...]:
    if resolve_i2v_profile() == "grok_primary":
        return (
            "grok",  # i2v_provider=grok · image_to_video 720p
            "ltx-i2v",  # only if canary 201
            "seedance-2-fast-i2v",  # when permission returns
        )
    return (
        "seedance-2-fast-i2v",
        "ltx-i2v",
        "grok",
    )


# Back-compat names used across codebase
DEFAULT_I2V_PROVIDER = "auto"  # resolved in validate via profile
DEFAULT_FRW_VIDEO_MODEL = "seedance-2-fast-i2v"
FRW_I2V_FALLBACK_CHAIN = frw_i2v_fallback_chain()
FRW_ENV_MODELS = frozenset(
    {
        "ltx-t2v",
        "seedance-2-fast-t2v",
        "byteplus-seedance-2-t2v",
        "legacy-text2video",  # classic FRW text2video — not preferred
        "auto",
    }
)
FRW_T2V_FALLBACK_CHAIN = (
    "ltx-t2v",
    "seedance-2-fast-t2v",
    "legacy-text2video",
)
# Per-shot production layer (P1 identity vs P5 synth beds)
SHOT_ROLES = frozenset({"hero", "env", "bridge", "insert"})
DEFAULT_SHOT_ROLE = "hero"
# Designed-post captions: zh default; zh_en dual line (requires nar_en or soft warn)
CAPTION_MODES = frozenset({"zh", "zh_en", "en"})
DEFAULT_CAPTION_MODE = "zh"
# Transition fluency: silk = soft glue; punchy = hard; cinematic = craft catalog + rhythm
TRANSITION_FLUENCIES = frozenset({"auto", "silk", "punchy", "cinematic"})
DEFAULT_TRANSITION_FLUENCY = "auto"
# Beat grammar — maps to ecchi-story / director packet spine
DRAMATIC_FUNCTIONS = frozenset(
    {
        "hook",
        "approach",
        "sensory",
        "reaction",
        "action",
        "afterglow",
        "bridge",
    }
)
MIN_LOGLINE_LEN = 8
MIN_EMOTIONAL_ARC = 3
# VO budget (ecchi-story / season production): hard gate on per-shot nar length.
# Chinese edge-TTS ≈ 3.5–4 chars/s; 55 chars ≈ 13s → heavy loop-stretch on 6s I2V.
# 2026-07-16 Kei: long nar → stream_loop → "boring replay". Prefer snappy ≤28.
MAX_NAR_CHARS = 55
RECOMMENDED_NAR_CHARS = 28  # snappy: fits ~6s I2V with loops=0 after pad
# Rough est: seconds ≈ chars / 4 for zh storyteller (floor 1.0)
NAR_CHARS_PER_SEC = 4.0
# Default I2V plate when duration_sec omitted
DEFAULT_DURATION_SEC = 6.0
# Soft report threshold (legacy); hard gate is est_vo_sec <= duration_sec + slack.
LOOP_RISK_VO_SEC = 5.5
# TTS estimate slack vs plate (actual edge-tts may drift slightly under estimate).
VO_PACING_SLACK_SEC = 0.5
# Beats that must never stream_loop in final (see edit_policy.plan_stretch forbid_loop).
NO_LOOP_DRAMATIC_FUNCTIONS = frozenset({"hook", "action"})


class FilmSpecError(ValueError):
    pass


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
            missing_acts = [key for key in ("setup", "confrontation", "resolution") if not act_cleaned.get(key)]
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


def validate_film_spec(
    spec: dict[str, Any],
    *,
    assign_missing_ids: bool,
    film_root: Any | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(spec, dict):
        raise FilmSpecError("film-spec must be a JSON object")
    _required_text(spec.get("title"), field="title")
    mode = _required_text(spec.get("vo_mode"), field="vo_mode").lower()
    if mode not in VO_MODES:
        raise FilmSpecError(f"film-spec vo_mode must be one of {sorted(VO_MODES)}")
    spec["vo_mode"] = mode
    validate_director_intent(spec)
    tts_backend = spec.get("tts_backend", "auto")
    if not isinstance(tts_backend, str) or tts_backend.lower() not in TTS_BACKENDS:
        raise FilmSpecError(f"film-spec tts_backend must be one of {sorted(TTS_BACKENDS)}")
    spec["tts_backend"] = tts_backend.lower()
    # Phase F: 中文说书默认钉 edge（避免 auto→external/ElevenLabs + Neural 翻车）
    if mode in ("storyteller", "hybrid") and spec["tts_backend"] == "auto":
        spec["tts_backend"] = "edge"
        notes = list(spec.get("_tts_notes") or [])
        notes.append("auto→edge for storyteller/hybrid (中文说书默认；显式 external/fish/… 可覆盖)")
        spec["_tts_notes"] = notes
    # I2V profile: grok_primary (Seedance outage) vs seedance_first
    i2v_profile = resolve_i2v_profile()
    spec["_i2v_profile"] = i2v_profile
    chain = frw_i2v_fallback_chain()
    raw_i2v = spec.get("i2v_provider", "auto")
    if not isinstance(raw_i2v, str) or raw_i2v.lower() not in I2V_PROVIDERS:
        raise FilmSpecError(f"film-spec i2v_provider must be one of {sorted(I2V_PROVIDERS)}")
    i2v_provider = raw_i2v.lower()
    if i2v_provider == "auto":
        i2v_provider = default_i2v_provider()
        i2v_notes = list(spec.get("_i2v_notes") or [])
        if i2v_profile == "grok_primary":
            i2v_notes.append(
                "auto→grok (AIFILM_I2V_PROFILE=grok_primary / Seedance unavailable: "
                "bulk image_to_video 720p; still=image_edit cast; register image_to_video)"
            )
        else:
            i2v_notes.append("auto→frw for bulk 2V (Seedance newvideo; Grok still for identity)")
        spec["_i2v_notes"] = i2v_notes
    # Soft warn if profile is grok_primary but user left i2v_provider=frw + seedance model
    if i2v_profile == "grok_primary" and i2v_provider == "frw":
        i2v_notes = list(spec.get("_i2v_notes") or [])
        i2v_notes.append(
            "WARN profile=grok_primary but i2v_provider=frw — Seedance may 403; "
            "prefer i2v_provider=grok or set AIFILM_I2V_PROFILE=seedance_first when open"
        )
        spec["_i2v_notes"] = i2v_notes
    spec["i2v_provider"] = i2v_provider
    # FRW video model (Seedance/LTX path). auto → seedance id kept as aspirational label
    raw_fvm = spec.get("frw_video_model", default_frw_video_model())
    if not isinstance(raw_fvm, str) or raw_fvm.lower() not in FRW_VIDEO_MODELS:
        raise FilmSpecError(f"film-spec frw_video_model must be one of {sorted(FRW_VIDEO_MODELS)}")
    fvm = raw_fvm.lower()
    if fvm == "auto":
        fvm = default_frw_video_model()
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            f"auto→{fvm} (label for when FRW seedance returns; "
            f"L1 active provider={i2v_provider}; never legacy img2video default)"
        )
        spec["_frw_video_notes"] = notes
    if fvm == "legacy-img2video":
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            "WARN legacy-img2video: old FRW template 348771… quality floor; "
            "FRW-only lifeboat when Seedance 403 and Grok unavailable; "
            "register frw_img2video — never claim seedance (2026-07-21); "
            "prefer grok 720p / ltx-i2v / seedance when open"
        )
        spec["_frw_video_notes"] = notes
    if fvm.startswith("ltx-"):
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            "LTX: width/height/duration/fps must be strings; "
            "9:16 use 720×1280 (probe-validated); avoid 768×1344; "
            "ltx-i2v/flf may 502 platform-side — fall back to grok"
        )
        spec["_frw_video_notes"] = notes
    spec["frw_video_model"] = fvm
    # Seedance defaults for agent CLI (aspect/resolution/duration)
    if "frw_aspect_ratio" not in spec or not spec.get("frw_aspect_ratio"):
        ar = str(spec.get("aspect_ratio") or DEFAULT_FRW_ASPECT)
        spec["frw_aspect_ratio"] = (
            "9:16"
            if ar in {"9:16", "9x16"}
            else ("16:9" if ar in {"16:9", "16x9"} else DEFAULT_FRW_ASPECT)
        )
    if "frw_resolution" not in spec or not spec.get("frw_resolution"):
        # fast-i2v template defaults 720p; do not invent 576
        spec["frw_resolution"] = DEFAULT_FRW_RESOLUTION
    if "frw_duration" not in spec or not spec.get("frw_duration"):
        spec["frw_duration"] = DEFAULT_FRW_DURATION
    # Always store as strings (LTX/API reject numbers)
    spec["frw_duration"] = str(spec.get("frw_duration") or DEFAULT_FRW_DURATION)
    if "frw_fps" not in spec or not spec.get("frw_fps"):
        if fvm.startswith("ltx-"):
            spec["frw_fps"] = DEFAULT_FRW_FPS
    else:
        spec["frw_fps"] = str(spec["frw_fps"])
    # LTX pixel size (seedance uses aspect+resolution labels instead)
    ar_frw = str(spec.get("frw_aspect_ratio") or DEFAULT_FRW_ASPECT)
    if fvm.startswith("ltx-"):
        if not spec.get("frw_width") or not spec.get("frw_height"):
            if ar_frw in {"9:16", "9x16"}:
                spec["frw_width"] = str(spec.get("frw_width") or DEFAULT_LTX_WIDTH)
                spec["frw_height"] = str(spec.get("frw_height") or DEFAULT_LTX_HEIGHT)
            elif ar_frw in {"16:9", "16x9"}:
                spec["frw_width"] = str(spec.get("frw_width") or "1280")
                spec["frw_height"] = str(spec.get("frw_height") or "720")
            else:
                spec["frw_width"] = str(spec.get("frw_width") or DEFAULT_LTX_WIDTH)
                spec["frw_height"] = str(spec.get("frw_height") or DEFAULT_LTX_HEIGHT)
        else:
            spec["frw_width"] = str(spec["frw_width"])
            spec["frw_height"] = str(spec["frw_height"])
    # Fallback chain note for agents (not auto-executed) — always refresh to profile
    spec["_frw_fallback_chain"] = list(chain)
    # Env / synth layer model (LTX T2V beds — no face import)
    raw_env = spec.get("frw_env_model", DEFAULT_FRW_ENV_MODEL)
    if not isinstance(raw_env, str) or raw_env.lower() not in FRW_ENV_MODELS:
        raise FilmSpecError(f"film-spec frw_env_model must be one of {sorted(FRW_ENV_MODELS)}")
    env_m = raw_env.lower()
    if env_m == "auto":
        env_m = DEFAULT_FRW_ENV_MODEL
        notes = list(spec.get("_frw_env_notes") or [])
        notes.append(f"auto→{env_m} for env/bridge/insert beds (no cast import)")
        spec["_frw_env_notes"] = notes
    if env_m == "legacy-text2video":
        notes = list(spec.get("_frw_env_notes") or [])
        notes.append("WARN legacy-text2video: classic FRW T2V; prefer ltx-t2v")
        spec["_frw_env_notes"] = notes
    spec["frw_env_model"] = env_m
    if "_frw_t2v_fallback_chain" not in spec:
        spec["_frw_t2v_fallback_chain"] = list(FRW_T2V_FALLBACK_CHAIN)
    # Layer routing summary for agents (P1 hero vs P5 synth)
    hero_primary = "grok_image_to_video_720p" if i2v_provider == "grok" else f"frw:{fvm}"
    spec["_layer_routing"] = {
        "i2v_profile": i2v_profile,
        "hero_still": "grok_image_edit_cast",
        "hero_motion_primary": hero_primary,
        "hero_i2v_provider": i2v_provider,
        "hero_motion_fallback": list(chain),
        "hero_motion_frw_only_lifeboat": FRW_I2V_FRW_ONLY_LIFEBOAT,
        "env_synth_primary": env_m,
        "env_synth_fallback": list(FRW_T2V_FALLBACK_CHAIN),
        "env_plate_cli": "aifilm env-plate --model ltx-t2v (FRW unlimited no-face)",
        "env_register_endpoint": "frw_ltx_t2v",
        "key_canary": (
            "optional while grok_primary; when reopening Seedance: "
            "balance + seedance-2-fast-i2v smoke + ltx-t2v; 403≠502"
        ),
        "register_endpoint_hero": (
            "image_to_video"
            if i2v_provider == "grok"
            else "frw_seedance_i2v|frw_ltx_*|frw_img2video"
        ),
        "designed_post": "hyperframes|remotion",
        "note": (
            "hero = face/identity via Grok only; env/bridge/insert → FRW ltx-t2v beds "
            "(template ltx-文生视频, verified completed); never T2V a face as identity; "
            "extract first frame from env plate for no-character keyframes"
        ),
    }
    # Caption language(s) for designed-post (HyperFrames/Remotion)
    raw_cap = spec.get("caption_mode", DEFAULT_CAPTION_MODE)
    if not isinstance(raw_cap, str) or raw_cap.lower() not in CAPTION_MODES:
        raise FilmSpecError(f"film-spec caption_mode must be one of {sorted(CAPTION_MODES)}")
    spec["caption_mode"] = raw_cap.lower()
    # Transition fluency (silk editorial glue vs punchy hard punctuation)
    raw_flu = spec.get("transition_fluency", DEFAULT_TRANSITION_FLUENCY)
    if not isinstance(raw_flu, str) or raw_flu.lower() not in TRANSITION_FLUENCIES:
        raise FilmSpecError(
            f"film-spec transition_fluency must be one of {sorted(TRANSITION_FLUENCIES)}"
        )
    flu = raw_flu.lower()
    if flu == "auto":
        # storyteller/色气 short: default silk on non-continue; horror punchy left to author
        tone_blob = " ".join(
            str(x)
            for x in (
                (spec.get("director_intent") or {}).get("tone")
                if isinstance(spec.get("director_intent"), dict)
                else "",
                spec.get("title") or "",
                spec.get("description") or "",
            )
        ).lower()
        if any(k in tone_blob for k in ("horror", "惊悚", "恐怖", "thriller", "dark")):
            flu = "punchy"
        else:
            flu = "silk"
        notes = list(spec.get("_transition_fluency_notes") or [])
        notes.append(f"auto→{flu} transition_fluency")
        spec["_transition_fluency_notes"] = notes
    spec["transition_fluency"] = flu
    allow_fallback = spec.get("tts_allow_network_fallback", False)
    if not isinstance(allow_fallback, bool):
        raise FilmSpecError("film-spec tts_allow_network_fallback must be boolean")
    native_volume = spec.get("native_audio_volume", 0.16)
    if not isinstance(native_volume, (int, float)) or isinstance(native_volume, bool):
        raise FilmSpecError("film-spec native_audio_volume must be a number between 0 and 1")
    if float(native_volume) < 0 or float(native_volume) > 1:
        raise FilmSpecError("film-spec native_audio_volume must be between 0 and 1")
    # Default silk dissolve when author omits transition_sec.  Keep this fact so
    # the voice-coupled strategy cannot turn an implicit global default into an
    # authored 0.40s hold just because one join is a mood_hold.
    transition_sec_authored = "transition_sec" in spec and spec.get("transition_sec") is not None
    edit_craft_authored = isinstance(spec.get("edit_craft"), list) or isinstance(
        spec.get("edit_crafts"), list
    )
    if not transition_sec_authored:
        spec["transition_sec"] = DEFAULT_TRANSITION_SEC
    try:
        spec["transition_sec"] = normalize_transition_sec(spec.get("transition_sec"))
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

    try:
        spec["transition_style"] = normalize_xfade_style(spec.get("transition_style"))
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Optional P2: per-join story transition intents (length n_shots-1 after shots known)
    # If omitted, auto-fill from dramatic_function sequence after shots validated.
    raw_intents = spec.get("transition_intents")
    if raw_intents is not None and not isinstance(raw_intents, list):
        raise FilmSpecError("transition_intents must be an array of hard|soft|hold")
    raw_styles = spec.get("transition_styles")
    if raw_styles is not None and not isinstance(raw_styles, list):
        raise FilmSpecError("transition_styles must be an array of xfade style names")

    default_intent = spec.get("transition_default", "soft")
    try:
        spec["transition_default"] = normalize_transition_intent(
            default_intent, field="transition_default"
        )
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

    # BGM: 色气/storyteller default rnb (R&B/Soul seductive). dark only for horror.
    intent_for_sound = (
        spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    )
    tone_txt = str((intent_for_sound or {}).get("tone") or "")
    try:
        if spec.get("sound_plan") is None:
            # Auto-inject so agents don't forget and fall into dark by accident
            sound = default_sound_plan_for_film(
                vo_mode=str(spec.get("vo_mode") or "storyteller"),
                tone=tone_txt,
                title=str(spec.get("title") or ""),
                description=str(spec.get("description") or ""),
            )
            sound["_notes"] = ["auto-injected default sound_plan (mood=rnb for 色气/storyteller)"]
        else:
            sound = validate_sound_plan(
                spec.get("sound_plan"),
                tone=tone_txt,
                title=str(spec.get("title") or ""),
                description=str(spec.get("description") or ""),
                vo_mode=str(spec.get("vo_mode") or ""),
            )
    except SoundPlanError as exc:
        raise FilmSpecError(str(exc)) from exc
    if sound is not None:
        # rnb family: pin sidechain so VO pauses breathe (Phase F; author can override)
        mood_l = str(sound.get("mood") or "").lower()
        if mood_l in {"rnb", "sensual", "soul", "seductive", "ecchi"} and not sound.get(
            "sidechain"
        ):
            sc = resolve_sidechain(sound, mood=mood_l)
            sound["sidechain"] = {
                "threshold": sc["threshold"],
                "ratio": sc["ratio"],
                "attack_ms": sc["attack_ms"],
                "release_ms": sc["release_ms"],
            }
            sn = list(sound.get("_notes") or [])
            sn.append(
                f"auto-injected rnb sidechain release_ms={sc['release_ms']:.0f} (VO pause breath)"
            )
            sound["_notes"] = sn
        spec["sound_plan"] = sound
        if sound.get("_notes"):
            spec.setdefault("_sound_plan_notes", list(sound.get("_notes") or []))

    scenes = spec.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise FilmSpecError("film-spec requires non-empty scenes")

    shots: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_axes: list[str] = []
    previous_viewpoints: list[str] = []
    previous_focal: str | None = None
    previous_viewpoint: str | None = None
    previous_look: str | None = None
    previous_end_pose: str | None = None
    # Cast ids for multi-stance (style-bible keys or director_intent.cast)
    cast_ids: list[str] = []
    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    raw_cast = di.get("cast") or di.get("characters") or spec.get("cast_ids")
    if isinstance(raw_cast, list):
        cast_ids = [str(x).strip() for x in raw_cast if str(x).strip()]
    elif isinstance(raw_cast, dict):
        cast_ids = [str(k).strip() for k in raw_cast if str(k).strip()]
    # style-bible may not be in film-spec; optional cast_masters on spec
    cm = spec.get("cast_masters")
    if isinstance(cm, dict):
        for k in cm:
            if str(k).strip() and str(k) not in cast_ids:
                cast_ids.append(str(k).strip())
    if not cast_ids:
        cast_ids = ["hero", "partner"]

    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise FilmSpecError(f"scene {scene_index} must be an object")
        scene_shots = scene.get("shots")
        if scene_shots is None:
            scene_shots = []
        if not isinstance(scene_shots, list):
            raise FilmSpecError(f"scene {scene_index} shots must be an array")
        for shot in scene_shots:
            if not isinstance(shot, dict):
                raise FilmSpecError(f"scene {scene_index} contains a non-object shot")
            if not shot.get("id") and assign_missing_ids:
                shot["id"] = f"shot{len(shots) + 1:02d}"
            try:
                shot_id = validate_identifier(shot.get("id"), field="shot id")
            except SecurityPolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            if shot_id in seen:
                raise FilmSpecError(f"duplicate shot id: {shot_id}")
            seen.add(shot_id)
            shot["nar"] = validate_nar_budget(shot.get("nar"), field=f"{shot_id}.nar")
            # v1.23: VO script lint — brochure phrase / AI-cadence / long-sentence warnings.
            # Advisory only (warnings); genre=product can elevate to hard gate.
            from vo_lint import lint_nar_text

            _vo_warnings = lint_nar_text(shot["nar"], shot_id=shot_id)
            if _vo_warnings:
                shot.setdefault("_vo_lint_warnings", [w.to_dict() for w in _vo_warnings])
            elif "_vo_lint_warnings" in shot:
                del shot["_vo_lint_warnings"]
            # Optional English line for dual captions (designed-post); not TTS-spoken by default
            nar_en = shot.get("nar_en")
            if nar_en is not None:
                if not isinstance(nar_en, str):
                    raise FilmSpecError(f"{shot_id}.nar_en must be a string")
                shot["nar_en"] = nar_en.strip()
            shot["est_vo_sec"] = estimate_nar_vo_sec(shot["nar"])
            shot["dramatic_function"] = validate_dramatic_function(
                shot.get("dramatic_function"),
                field=f"{shot_id}.dramatic_function",
            )
            # Layer role: hero (identity I2V) vs env/bridge/insert (LTX T2V synth beds)
            raw_role = shot.get("shot_role")
            if raw_role is None or (isinstance(raw_role, str) and not raw_role.strip()):
                dsl0 = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
                cast0 = dsl0.get("cast") if isinstance(dsl0, dict) else None
                has_cast = bool(cast0)
                # subject alone is weak signal — default hero for safety (identity first)
                fn0 = shot["dramatic_function"]
                if fn0 == "bridge" and not has_cast:
                    role = "env"
                elif fn0 == "bridge":
                    role = "bridge"
                else:
                    role = DEFAULT_SHOT_ROLE
            else:
                if not isinstance(raw_role, str) or raw_role.lower() not in SHOT_ROLES:
                    raise FilmSpecError(f"{shot_id}.shot_role must be one of {sorted(SHOT_ROLES)}")
                role = raw_role.lower()
            shot["shot_role"] = role
            # Recommend engine per layer (agent CLI; not auto-dispatched)
            if role == "hero":
                shot["_recommended_engine"] = {
                    "still": "grok_image_edit_cast",
                    "motion": "frw_video_model_i2v_or_grok",
                    "frw_model_field": "frw_video_model",
                    "forbid": ["ltx-t2v_as_face", "legacy-img2video_default"],
                }
            else:
                shot["_recommended_engine"] = {
                    "still": "optional_empty_or_style_only",
                    "motion": "frw_env_model_t2v",
                    "frw_model_field": "frw_env_model",
                    "primary": DEFAULT_FRW_ENV_MODEL,
                    "forbid": ["claim_identity_lock_from_t2v"],
                }
            # B1: motion/size/axis + character stance (focal/viewpoint/look_axis)
            try:
                cov = apply_coverage_defaults_to_shot(
                    shot,
                    dramatic_function=shot["dramatic_function"],
                    shot_index=len(shots),
                    previous_axes=previous_axes,
                    previous_focal=previous_focal,
                    previous_viewpoints=previous_viewpoints,
                    previous_viewpoint=previous_viewpoint,
                    previous_look=previous_look,
                    previous_end_pose=previous_end_pose,
                    cast_ids=cast_ids,
                )
                ax = str((cov or {}).get("camera_axis") or "").strip()
                if ax:
                    previous_axes.append(ax)
                previous_focal = str((cov or {}).get("focal_character") or previous_focal or "")

                vp = str((cov or {}).get("viewpoint") or "")
                if vp:
                    previous_viewpoints.append(vp)
                    previous_viewpoint = vp
                else:
                    previous_viewpoint = previous_viewpoint or ""

                previous_look = str((cov or {}).get("look_axis") or previous_look or "")

                ep = str(shot.get("dsl", {}).get("end_pose") or shot.get("end_pose") or "")
                if ep:
                    previous_end_pose = ep

            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            dsl = shot.get("dsl")
            if not isinstance(dsl, dict) or not dsl:
                raise FilmSpecError(f"{shot_id} requires non-empty dsl object")
            # Motion language is required for I2V dynamics (camera + body)
            motion = dsl.get("motion")
            try:
                dsl["motion"] = validate_motion(motion, field=f"{shot_id}.dsl.motion")
            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            duration = shot.get("duration_sec")
            if duration is None:
                duration_value = DEFAULT_DURATION_SEC
                shot["duration_sec"] = DEFAULT_DURATION_SEC
            else:
                try:
                    duration_value = float(duration)
                except (TypeError, ValueError) as exc:
                    raise FilmSpecError(f"{shot_id}.duration_sec must be a number") from exc
                if duration_value <= 0 or duration_value > 60:
                    raise FilmSpecError(f"{shot_id}.duration_sec must be > 0 and <= 60")
                shot["duration_sec"] = duration_value
            # S1 hard gate: VO estimate must fit the I2V plate (no loop-to-fill).
            est_vo = float(shot["est_vo_sec"])
            if est_vo > duration_value + VO_PACING_SLACK_SEC:
                raise FilmSpecError(
                    f"{shot_id} vo_pacing: est_vo_sec={est_vo} > duration_sec={duration_value} "
                    f"(slack {VO_PACING_SLACK_SEC}s). Shorten nar (≤{RECOMMENDED_NAR_CHARS} chars for 6s), "
                    f"set duration_sec to 10, or split into another shot — do not rely on stream_loop."
                )
            shots.append(shot)
    if not shots:
        raise FilmSpecError("film-spec requires at least one shot")

    # Aggregate VO budget report (non-blocking summary for agents / status)
    total_est = sum(float(s.get("est_vo_sec") or 0) for s in shots)
    long_recommended = [
        s["id"] for s in shots if len(str(s.get("nar") or "")) > RECOMMENDED_NAR_CHARS
    ]
    # Soft advisory: still surface shots that sit near the 6s plate edge.
    loop_risk = [
        s["id"]
        for s in shots
        if float(s.get("est_vo_sec") or 0) > LOOP_RISK_VO_SEC
        and float(s.get("duration_sec") or DEFAULT_DURATION_SEC) <= 6.5
    ]
    no_loop_beats = [
        s["id"]
        for s in shots
        if str(s.get("dramatic_function") or "") in NO_LOOP_DRAMATIC_FUNCTIONS
    ]
    # Scene-adaptive audio recipes (policy + per-shot recipe; soft degrade)
    try:
        caps = probe_caps_for_root(film_root)
        apply_audio_recipes_to_spec(
            spec,
            shots,
            lipsync_ready=bool(caps.get("lipsync_ready")),
            music_library=bool(caps.get("music_library")),
            sung_provider_ready=bool(caps.get("sung_provider_ready")),
        )
    except AudioRecipeError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Adult flesh SFX → sound_plan events (after voice_tracks auto sound_cues)
    try:
        heat_for_sfx = str(spec.get("heat_scale") or "").strip().lower() or None
        sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else None
        if sp is None and heat_for_sfx in {"max", "hot"}:
            sp = default_sound_plan_for_film(
                vo_mode=str(spec.get("vo_mode") or "storyteller"),
                tone=str((spec.get("director_intent") or {}).get("tone") or ""),
                title=str(spec.get("title") or ""),
                description=str(spec.get("description") or ""),
            )
        if isinstance(sp, dict):
            sp = inject_auto_sfx_if_empty(sp, shots, heat_scale=heat_for_sfx)
            sp = inject_sex_sfx_from_shots(sp, shots, heat_scale=heat_for_sfx)
            spec["sound_plan"] = sp
            if sp.get("_notes"):
                notes = list(spec.get("_sound_plan_notes") or [])
                for n in sp.get("_notes") or []:
                    if n not in notes:
                        notes.append(n)
                spec["_sound_plan_notes"] = notes
    except Exception as exc:  # noqa: BLE001 — soft
        notes = list(spec.get("_sound_plan_notes") or [])
        notes.append(f"sex_sfx inject soft-fail: {exc}")
        spec["_sound_plan_notes"] = notes

    # Voice-coupled editorial strategy (after vocal_color exists)
    try:
        from edit_strategy import EditStrategyError, apply_edit_strategy_to_spec

        apply_edit_strategy_to_spec(spec)
        if not transition_sec_authored:
            spec["transition_sec"] = DEFAULT_TRANSITION_SEC
    except EditStrategyError as exc:
        raise FilmSpecError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — soft: never block write-spec
        notes = list(spec.get("_edit_strategy_errors") or [])
        notes.append(str(exc))
        spec["_edit_strategy_errors"] = notes

    spec["_vo_budget"] = {
        "max_nar_chars": MAX_NAR_CHARS,
        "recommended_nar_chars": RECOMMENDED_NAR_CHARS,
        "loop_risk_vo_sec": LOOP_RISK_VO_SEC,
        "vo_pacing_slack_sec": VO_PACING_SLACK_SEC,
        "shot_count": len(shots),
        "total_est_vo_sec": round(total_est, 2),
        "shots_over_recommended": long_recommended,
        "loop_risk_shots": loop_risk,
        "no_loop_beats": no_loop_beats,
        "note": (
            "Hard: est_vo_sec ≤ duration_sec+slack (vo_pacing). "
            "Prefer nar≤28 so final stretch uses loops=0. "
            "hook/action never stream_loop in final. Grow runtime by adding shots."
        ),
    }

    # Validate or auto-suggest story join intents now that shot count is known
    expected = max(0, len(shots) - 1)
    chain_modes: list[str] = []
    cut_ons: list[str] = []
    scene_ids: list[str] = []
    # rebuild scene index per shot (scenes order)
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sid_label = str(scene.get("id") or scene.get("title") or f"scene{si}")
        for sh in scene.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            # only count shots that made it into validated `shots` list by id
            pass
    # Prefer validated shots list for chain/cut; scene membership from original scenes
    shot_to_scene: dict[str, str] = {}
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sid_label = str(scene.get("id") or scene.get("title") or f"scene{si}")
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                shot_to_scene[str(sh["id"])] = sid_label
    for s in shots:
        dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
        chain_modes.append(str((dsl or {}).get("chain_mode") or "").strip().lower())
        cut_ons.append(str((dsl or {}).get("cut_on") or "").strip().lower())
        scene_ids.append(shot_to_scene.get(str(s.get("id") or ""), "scene0"))

    # Editorial craft plan (资深剪辑语法) — always materialize for agent visibility
    beats = [str(s.get("dramatic_function") or "bridge") for s in shots]
    flu = str(spec.get("transition_fluency") or "auto")
    # cinematic fluency uses craft-rich suggestions (same catalog, anti soft-run)
    craft_flu = "cinematic" if flu in {"silk", "cinematic", "auto"} else flu
    raw_crafts = spec.get("edit_craft") or spec.get("edit_crafts")
    crafts: list[str] = []
    focals_for_craft = [
        str(
            (
                (s.get("dsl") or {}).get("focal_character")
                if isinstance(s.get("dsl"), dict)
                else None
            )
            or s.get("focal_character")
            or "hero"
        )
        for s in shots
    ]
    viewpoints_for_craft = [
        str(
            ((s.get("dsl") or {}).get("viewpoint") if isinstance(s.get("dsl"), dict) else None)
            or s.get("viewpoint")
            or "objective"
        )
        for s in shots
    ]
    if raw_crafts is not None:
        if not isinstance(raw_crafts, list) or len(raw_crafts) != expected:
            raise FilmSpecError(
                f"edit_craft length must be n_shots-1={expected}; got "
                f"{len(raw_crafts) if isinstance(raw_crafts, list) else type(raw_crafts)}"
            )
        try:
            crafts = [
                normalize_edit_craft(x, field=f"edit_craft[{i}]") for i, x in enumerate(raw_crafts)
            ]
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        spec["_edit_craft_source"] = "author" if edit_craft_authored else "craft_suggest"
    elif expected > 0:
        try:
            crafts = suggest_edit_crafts(
                beats,
                chain_modes=chain_modes,
                cut_ons=cut_ons,
                scene_ids=scene_ids,
                fluency=craft_flu if flu != "punchy" else "punchy",
                focals=focals_for_craft,
                viewpoints=viewpoints_for_craft,
            )
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        spec["_edit_craft_source"] = "craft_suggest"
    if crafts:
        # continue seams must stay HARD-intent crafts (smash/insert/montage ok as labels)
        hard_family = {
            "match_cut",
            "cut_on_action",
            "smash_cut",
            "contrast_cut",
            "insert_cut",
            "montage_jump",
        }
        for i, c in enumerate(crafts):
            next_chain = chain_modes[i + 1] if i + 1 < len(chain_modes) else ""
            if next_chain in {"continue", "match", "match_cut", "byte"} and c not in hard_family:
                crafts[i] = (
                    "cut_on_action"
                    if (cut_ons[i + 1] if i + 1 < len(cut_ons) else "")
                    in {"mid_motion", "mid-action", "action"}
                    else "match_cut"
                )
        spec["edit_craft"] = crafts
        spec["_edit_craft_plan"] = [
            {
                "join_index": i,
                "craft": c,
                "why": _CRAFT_WHY.get(c, ""),
                "intent": edit_crafts_to_intents([c])[0],
            }
            for i, c in enumerate(crafts)
        ]

    if raw_intents is not None:
        if len(raw_intents) != expected:
            raise FilmSpecError(
                f"transition_intents length must be n_shots-1={expected}; got {len(raw_intents)}"
            )
        try:
            author_intents = [
                normalize_transition_intent(x, field=f"transition_intents[{i}]")
                for i, x in enumerate(raw_intents)
            ]
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        # continue seams always hard — even if author wrote soft/hold (男娘咖啡厅)
        fixed, fix_notes = enforce_continue_hard_joins(author_intents, chain_modes)
        spec["transition_intents"] = fixed
        spec["_transition_intents_source"] = "author"
        if fix_notes:
            spec["_transition_continue_hard_fixes"] = fix_notes
    elif expected > 0:
        try:
            if crafts:
                auto = edit_crafts_to_intents(crafts)
            else:
                auto = suggest_transition_intents(
                    beats,
                    chain_modes=chain_modes,
                    fluency=flu,
                    cut_ons=cut_ons,
                    scene_ids=scene_ids,
                )
            fixed, fix_notes = enforce_continue_hard_joins(auto, chain_modes)
            spec["transition_intents"] = [
                normalize_transition_intent(x, field=f"transition_intents[{i}]")
                for i, x in enumerate(fixed)
            ]
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        spec["_transition_intents_source"] = "edit_craft" if crafts else "beat_suggest"
        if fix_notes:
            spec["_transition_continue_hard_fixes"] = fix_notes

    # Dual caption soft report (not hard fail — agent can fill nar_en later)
    cap_mode = str(spec.get("caption_mode") or "zh")
    if cap_mode == "zh_en":
        missing_en = [str(s.get("id")) for s in shots if not str(s.get("nar_en") or "").strip()]
        spec["_caption_mode_report"] = {
            "mode": "zh_en",
            "missing_nar_en": missing_en,
            "ok": len(missing_en) == 0,
            "note": "zh_en designed-post needs shot.nar_en for dual lines; agent fills EN",
        }
    else:
        spec["_caption_mode_report"] = {"mode": cap_mode, "ok": True}

    # Per-join xfade styles (anti soft-soup of only fade)
    intents_for_styles = spec.get("transition_intents")
    if expected > 0 and isinstance(intents_for_styles, list):
        if raw_styles is not None:
            try:
                spec["transition_styles"] = normalize_transition_styles(
                    list(raw_styles),
                    n_joins=expected,
                    fallback=str(spec.get("transition_style") or "fade"),
                )
            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            spec["_transition_styles_source"] = "author"
        else:
            try:
                auto_styles = suggest_transition_styles(
                    [str(x) for x in intents_for_styles],
                    dramatic_functions=beats,
                    edit_crafts=crafts if crafts else None,
                )
                spec["transition_styles"] = normalize_transition_styles(
                    auto_styles,
                    n_joins=expected,
                    fallback=str(spec.get("transition_style") or "fade"),
                )
            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            spec["_transition_styles_source"] = "edit_craft" if crafts else "beat_suggest"

    # Layer identity soft report: T2V/env beds must not claim hero face lock
    layer_issues: list[dict[str, Any]] = []
    hero_n = sum(1 for s in shots if s.get("shot_role") == "hero")
    env_n = sum(1 for s in shots if s.get("shot_role") in {"env", "bridge", "insert"})
    for s in shots:
        sid = str(s.get("id") or "")
        role = str(s.get("shot_role") or "hero")
        dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
        if role == "hero":
            # hero should have identity anchors for agent
            if not str(dsl.get("subject") or "").strip() and not dsl.get("cast"):
                layer_issues.append(
                    {
                        "code": "HERO_MISSING_IDENTITY_ANCHOR",
                        "severity": "warning",
                        "shot_id": sid,
                        "message": (
                            f"{sid} shot_role=hero but no dsl.cast/subject — "
                            "lock cast master before I2V"
                        ),
                    }
                )
        elif role in {"env", "insert", "bridge"}:
            # warn if author writes face-fill language on env bed
            blob = " ".join(
                str(dsl.get(k) or "") for k in ("subject", "action", "motion", "story_beat")
            ).lower()
            if any(
                k in blob
                for k in (
                    "close-up face",
                    "portrait face",
                    "fills frame",
                    "hero face",
                    "cast master",
                )
            ):
                layer_issues.append(
                    {
                        "code": "ENV_BED_FACE_LANGUAGE",
                        "severity": "warning",
                        "shot_id": sid,
                        "message": (
                            f"{sid} shot_role={role} looks face-centric — "
                            "use hero I2V for identity; keep LTX T2V face-free"
                        ),
                    }
                )
    spec["_layer_report"] = {
        "hero_shots": hero_n,
        "env_synth_shots": env_n,
        "issues": layer_issues,
        "ok": len(layer_issues) == 0,
        "note": (
            "hero→cast still + I2V (Seedance/Grok); "
            "env/bridge/insert→LTX T2V beds for splice (no face import)"
        ),
    }

    # Continuity lint (non-strict by default; attach report on spec)
    cont = lint_continuity(shots)
    spec["_continuity_lint"] = {
        "ok": cont["ok"],
        "codes": cont["codes"],
        "error_count": cont["error_count"],
        "warning_count": cont["warning_count"],
        "issues": cont["issues"],
    }
    if spec.get("continuity_strict") is True and not cont["ok"]:
        raise FilmSpecError(
            "continuity lint failed (continuity_strict): " + ",".join(cont["codes"])
        )

    # Character stance / multi-POV (soft; character-stance.md)
    stance = lint_character_stance(shots)
    spec["_character_stance"] = {
        "ok": stance.get("ok"),
        "codes": stance.get("codes"),
        "warning_count": stance.get("warning_count"),
        "issues": stance.get("issues"),
        "viewpoint_set": stance.get("viewpoint_set"),
        "focal_set": stance.get("focal_set"),
        "note": (
            "Soft: rotate viewpoint (ots/reverse/reaction/pov); "
            "reaction may flip focal_character; reverse prefers focal shift. "
            "See references/character-stance.md"
        ),
    }
    if spec.get("stance_strict") is True and not stance.get("ok"):
        raise FilmSpecError(
            "character stance lint failed (stance_strict): " + ",".join(stance.get("codes") or [])
        )

    # Performance / subtext (soft; performance_strict raises) — the director's
    # answer to "the camera moves, but what is the character's interior A→B?"
    # Mirrors drama-graph SHOT_PERFORMANCE_MISSING so the production contract
    # and canonical graph share one standard.
    perf = lint_performance(shots)
    spec["_performance_lint"] = {
        "ok": perf["ok"],
        "codes": perf["codes"],
        "warning_count": perf["warning_count"],
        "issues": perf["issues"],
        "note": (
            "Soft: hero shots should carry subtext / playable_action / body_state. "
            "I2V moves bodies; performance intent makes them act. "
            "Set performance_strict=true to hard-fail. See principles.md P0/P4"
        ),
    }
    if spec.get("performance_strict") is True and not perf["ok"]:
        raise FilmSpecError(
            "performance lint failed (performance_strict): " + ",".join(perf["codes"])
        )

    # Director decision board per scene (soft; scene_strict raises) — mirrors
    # drama-graph beat.director_board. A scene without authored emotional_turn /
    # audience_question / coverage_strategy / cut_intent has been pre-shot
    # without a director's pass.
    board = lint_director_board(scenes)
    spec["_director_board_lint"] = {
        "ok": board["ok"],
        "codes": board["codes"],
        "warning_count": board["warning_count"],
        "issues": board["issues"],
        "note": (
            "Soft: each scene should author director_board (emotional_turn / "
            "audience_question / coverage_strategy / cut_intent). "
            "Set scene_strict=true to require approval_state=approved before bulk."
        ),
    }
    if spec.get("scene_strict") is True and not board["ok"]:
        raise FilmSpecError(
            "director board lint failed (scene_strict): " + ",".join(board["codes"])
        )

    # VO–motion link / anti-fatigue (soft; lessons-2026-07-17-vo-motion-link)
    intents = spec.get("transition_intents")
    if not isinstance(intents, list):
        intents = None
    vml = lint_vo_motion_link(shots, transition_intents=intents)
    styles_for_lint = spec.get("transition_styles")
    if isinstance(styles_for_lint, list):
        stl = lint_transition_styles(
            [str(x) for x in styles_for_lint],
            join_intents=[str(x) for x in intents] if intents else None,
        )
        if stl.get("issues"):
            vml = {
                **vml,
                "issues": list(vml.get("issues") or []) + list(stl.get("issues") or []),
                "codes": sorted(set(vml.get("codes") or []) | set(stl.get("codes") or [])),
                "warning_count": int(vml.get("warning_count") or 0)
                + int(stl.get("warning_count") or 0),
                "ok": bool(vml.get("ok")) and bool(stl.get("ok")),
            }
    spec["_vo_motion_link"] = {
        "ok": vml["ok"],
        "codes": vml["codes"],
        "warning_count": vml["warning_count"],
        "issues": vml["issues"],
        "note": (
            "Soft: primary action leads micro fillers; rotate camera_axis; "
            "continue joins force hard; avoid SOFT_SOUP / STYLE_SOUP / CAMERA_AXIS_FLAT. "
            "See lessons-2026-07-20-transition-motion-v2.md"
        ),
    }
    # Meaningful motion: dynamics must carry beat-readable story
    mm = lint_meaningful_motion(shots)
    spec["_meaningful_motion"] = {
        "ok": mm["ok"],
        "codes": mm["codes"],
        "warning_count": mm["warning_count"],
        "issues": mm["issues"],
        "note": (
            "Soft: each shot motion must answer the beat's story question "
            "(not aesthetic blink/push-in only). Prefer dsl.visible_change + story_beat. "
            "See references/lessons-2026-07-20-meaningful-motion.md"
        ),
    }
    if spec.get("meaningful_motion_strict") is True and mm["warning_count"] > 0:
        raise FilmSpecError(
            "meaningful motion lint failed (meaningful_motion_strict): "
            + ",".join(mm["codes"] or ["MOTION"])
        )

    # Content channels: keep spoken text, visible performance and motion apart.
    channel_report = lint_content_channels(shots)
    spec["_content_channels"] = channel_report
    if spec.get("content_channels_strict") is True and not channel_report["ok"]:
        raise FilmSpecError(
            "content channel lint failed (content_channels_strict): "
            + ",".join(channel_report["codes"] or ["CONTENT_CHANNEL"])
        )

    # Director rhythm: hook timing, coverage repetition, size pressure, button.
    target_duration = spec.get("target_duration")
    rhythm = lint_rhythm(shots, target_duration=float(target_duration) if target_duration else None)
    spec["_rhythm"] = {
        "ok": rhythm["ok"],
        "codes": rhythm["codes"],
        "warning_count": rhythm["warning_count"],
        "issues": rhythm["issues"],
        "note": "Advisory by default; set rhythm_strict=true after director grammar is authored.",
    }
    if spec.get("rhythm_strict") is True and rhythm["warning_count"] > 0:
        raise FilmSpecError(
            "rhythm lint failed (rhythm_strict): " + ",".join(rhythm["codes"] or ["RHYTHM"])
        )
    # Frame chain (soft; lessons-2026-07-20-frame-chain) — soft/hold joins need end→start poses
    fch = lint_frame_chain(shots, transition_intents=intents)
    spec["_frame_chain"] = {
        "ok": fch["ok"],
        "codes": fch["codes"],
        "warning_count": fch["warning_count"],
        "issues": fch["issues"],
        "note": (
            "Soft/hold: end_pose→start_pose; continue join next keyframe MUST byte-reuse "
            "prev approved last frame (extract-frame --promote-keyframe). "
            "Do NOT restart from cast. Forbidden: dissolve/freeze/reverse/insert to hide breaks. "
            "Long-form requires continuity_chain.md — see references/continuity_chain.md"
        ),
    }
    if spec.get("frame_chain_strict") is True and fch["warning_count"] > 0:
        raise FilmSpecError(
            "frame chain lint failed (frame_chain_strict): "
            + ",".join(fch["codes"] or ["FRAME_CHAIN"])
        )
    # Long-form flag for agents (doc creation happens in write-spec CLI with root path)
    spec["_long_form"] = is_long_form(spec, shots)
    if spec.get("vo_motion_strict") is True and vml["warning_count"] > 0:
        raise FilmSpecError(
            "vo_motion_link lint failed (vo_motion_strict): " + ",".join(vml["codes"])
        )

    # Framing iron (soft; sediment from ai-film-cn head-crop discipline)
    frm = lint_framing_iron(shots)
    spec["_framing_lint"] = {
        "ok": frm["ok"],
        "codes": frm["codes"],
        "warning_count": frm["warning_count"],
        "error_count": frm["error_count"],
        "issues": frm["issues"],
        "note": frm.get("note"),
    }
    if spec.get("framing_strict") is True and (frm["warning_count"] > 0 or frm["error_count"] > 0):
        raise FilmSpecError(
            "framing iron lint failed (framing_strict): " + ",".join(frm["codes"] or ["FRAMING"])
        )

    safe_area = lint_vertical_safe_area(shots)
    spec["_vertical_safe_area"] = {
        "ok": safe_area["ok"],
        "codes": safe_area["codes"],
        "warning_count": safe_area["warning_count"],
        "issues": safe_area["issues"],
        "note": "Declare platform UI, subtitle, subject and prop-safe zones for 9:16 shots.",
    }
    if spec.get("vertical_safe_area_strict") is True and safe_area["warning_count"] > 0:
        raise FilmSpecError(
            "vertical safe-area lint failed (vertical_safe_area_strict): "
            + ",".join(safe_area["codes"] or ["VERTICAL_SAFE_AREA"])
        )

    # Heat + cast: elastic (no auto-pin heat_scale; metrics optional)
    try:
        heat_scale = normalize_heat_scale(spec.get("heat_scale"), default=None)
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc
    intent = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    # Do NOT auto-force heat_scale from keywords — agent/user sets it from the brief.
    if heat_scale is not None:
        spec["heat_scale"] = heat_scale
    # heat_phase fill only when asked (or when heat_scale already set and heat_phase_auto≠false)
    heat_phase_auto = spec.get("heat_phase_auto")
    if heat_phase_auto is True or (heat_scale is not None and heat_phase_auto is not False):
        filled_hp = apply_heat_phase_defaults(shots)
        if filled_hp:
            notes = list(spec.get("_heat_notes") or [])
            notes.append(f"heat_phase filled (soft): {','.join(filled_hp[:12])}")
            spec["_heat_notes"] = notes

    heat_advise = bool(spec.get("heat_arc_advise") is True)
    audience_profile = None
    if isinstance(intent.get("audience_profile"), str):
        audience_profile = intent.get("audience_profile")
    elif isinstance(spec.get("audience_profile"), str):
        audience_profile = spec.get("audience_profile")
    coitus_grammar = (
        spec.get("coitus_grammar") if isinstance(spec.get("coitus_grammar"), dict) else None
    )
    # 卸装阶梯延续：前镜状态继承；衣服不回穿（lint HEAT_WARDROBE_RE_DRESS）
    wardrobe_cont = apply_wardrobe_continuity(shots, heat_scale=heat_scale)
    if (
        wardrobe_cont.get("filled_ids")
        or wardrobe_cont.get("bumped_ids")
        or wardrobe_cont.get("clamped_ids")
        or wardrobe_cont.get("start_pose_ids")
    ):
        notes = list(spec.get("_heat_notes") or [])
        bits = []
        if wardrobe_cont.get("filled_ids"):
            bits.append("wardrobe inherit: " + ",".join(wardrobe_cont["filled_ids"][:12]))
        if wardrobe_cont.get("bumped_ids"):
            bits.append("wardrobe undress-bump: " + ",".join(wardrobe_cont["bumped_ids"][:12]))
        if wardrobe_cont.get("clamped_ids"):
            bits.append("wardrobe re-dress CLAMPED: " + ",".join(wardrobe_cont["clamped_ids"][:12]))
        if wardrobe_cont.get("start_pose_ids"):
            bits.append(
                "start_pose undress-lock: " + ",".join(wardrobe_cont["start_pose_ids"][:12])
            )
        notes.append("; ".join(bits))
        spec["_heat_notes"] = notes
    spec["_wardrobe_continuity"] = wardrobe_cont
    # spice_level default from heat/audience
    try:
        from edit_policy import HARDCORE_CRAFT_SPINE, normalize_spice_level
    except Exception:  # pragma: no cover
        normalize_spice_level = None  # type: ignore
        HARDCORE_CRAFT_SPINE = ()  # type: ignore
    spice_level = spec.get("spice_level")
    if normalize_spice_level is not None:
        resolved_spice = normalize_spice_level(
            spice_level, heat_scale=heat_scale, audience_profile=audience_profile
        )
        if resolved_spice and not spice_level:
            spec["spice_level"] = resolved_spice
            spice_level = resolved_spice
        elif spice_level:
            spice_level = str(spice_level).strip().lower()

    # Hardcore flat craft → inject montage spine (unless lock_craft)
    craft_raw = spec.get("edit_craft")
    craft_list: list[str] = []
    if isinstance(craft_raw, list):
        craft_list = [str(c) for c in craft_raw if str(c).strip()]
    elif isinstance(craft_raw, str) and craft_raw.strip():
        craft_list = [craft_raw.strip()]
    ap_l = str(audience_profile or "").strip().lower()
    hardcore_aud = ap_l in {"hardcore_male", "hardcore", "重口男向"}
    lock_craft = False
    es = spec.get("edit_strategy") if isinstance(spec.get("edit_strategy"), dict) else {}
    lock_craft = bool(es.get("lock_craft"))
    if (
        hardcore_aud
        and heat_scale == "max"
        and not lock_craft
        and (len(set(c.lower() for c in craft_list)) < 4 or not craft_list)
    ):
        n_join = max(1, len(shots) - 1)
        spine = list(HARDCORE_CRAFT_SPINE)
        while len(spine) < n_join:
            spine.extend(HARDCORE_CRAFT_SPINE)
        craft_list = spine[:n_join]
        spec["edit_craft"] = craft_list
        notes = list(spec.get("_heat_notes") or [])
        notes.append("hardcore edit_craft spine injected (montage/insert/smash)")
        spec["_heat_notes"] = notes

    # Prefer story-normalize raw for fidelity check when present on disk
    source_excerpt = (
        str(
            spec.get("source_script")
            or spec.get("source_excerpt")
            or (spec.get("_plan") or {}).get("raw_excerpt")
            or ""
        ).strip()
        or None
    )
    if film_root is not None and not source_excerpt:
        try:
            from pathlib import Path as _P

            norm_path = _P(film_root) / "receipts" / "story-normalize.json"
            if norm_path.is_file():
                import json as _json

                norm = _json.loads(norm_path.read_text(encoding="utf-8"))
                if isinstance(norm, dict):
                    source_excerpt = (
                        str(norm.get("raw_excerpt") or norm.get("logline") or "").strip() or None
                    )
        except Exception:
            source_excerpt = source_excerpt

    heat_rep = lint_heat_arc(
        shots,
        heat_scale=heat_scale,
        intimacy_min_ratio=spec.get("intimacy_min_ratio"),
        setup_max_ratio=spec.get("setup_max_ratio"),
        sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
        audience_profile=audience_profile,
        advise=heat_advise,
        coitus_grammar=coitus_grammar,
        spice_level=str(spice_level) if spice_level else None,
        edit_craft=craft_list or None,
        source_excerpt=source_excerpt,
    )
    spec["_heat_arc"] = heat_rep
    if spec.get("heat_arc_strict") is True and heat_rep["warning_count"] > 0:
        raise FilmSpecError(
            "heat arc lint failed (heat_arc_strict): " + ",".join(heat_rep["codes"] or ["HEAT"])
        )
    # P0 user-source fidelity only protects actual user source, never stock plans.
    fidelity_strict = spec.get("user_source_fidelity_strict")
    if fidelity_strict is None:
        fidelity_strict = heat_scale == "max" and bool(source_excerpt)
    if fidelity_strict is True and not source_excerpt:
        raise FilmSpecError(
            "user source fidelity requires source_excerpt when user_source_fidelity_strict=true"
        )
    fid_codes = [c for c in (heat_rep.get("codes") or []) if str(c).startswith("USER_SOURCE_")]
    if fidelity_strict is True and fid_codes:
        raise FilmSpecError(
            "user source fidelity failed (user_source_fidelity_strict): "
            + ",".join(fid_codes)
            + " — 用户原文被 adult-max 库存旁白覆盖。保留用户诗白/对白/专名；"
            "荤梗只可补后缀。See lessons-2026-07-22-user-source-fidelity.md"
        )
    sex_floor_strict = spec.get("sex_floor_strict")
    if sex_floor_strict is None:
        sex_floor_strict = heat_scale == "max"

    if "HEAT_SEX_DURATION_LOW" in (heat_rep.get("codes") or []):
        # Proactive orchestration: Auto-extend act/climax shots to meet ratio
        act_shots = [
            sh
            for sh in shots
            if isinstance(sh, dict)
            and str(sh.get("heat_phase") or "").strip().lower() in {"act", "climax"}
        ]
        if act_shots:
            for sh in act_shots:
                sh["duration_sec"] = max(
                    10.0, float(sh.get("duration_sec") or DEFAULT_DURATION_SEC)
                )
            # Re-lint after auto-extension
            heat_rep = lint_heat_arc(
                shots,
                heat_scale=heat_scale,
                intimacy_min_ratio=spec.get("intimacy_min_ratio"),
                setup_max_ratio=spec.get("setup_max_ratio"),
                sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
                audience_profile=audience_profile,
                advise=heat_advise,
                coitus_grammar=coitus_grammar,
                spice_level=str(spice_level) if spice_level else None,
                edit_craft=craft_list or None,
            )
            spec["_heat_arc"] = heat_rep

    if sex_floor_strict is True and "HEAT_SEX_DURATION_LOW" in (heat_rep.get("codes") or []):
        ratio = heat_rep.get("sex_duration_ratio")
        floor = heat_rep.get("sex_duration_floor")
        raise FilmSpecError(
            "sex duration floor failed (sex_floor_strict): HEAT_SEX_DURATION_LOW "
            f"sex_duration_ratio={ratio} floor={floor} — "
            "raise act+climax duration_sec share to ≥30% of total (or set "
            "sex_min_duration_ratio / sex_floor_strict:false). See ecchi-story.md"
        )
    # Sex wardrobe: act/climax must undress; continuity monotonic (衣服不回穿); hard on max.
    sex_wardrobe_strict = spec.get("sex_wardrobe_strict")
    if sex_wardrobe_strict is None:
        sex_wardrobe_strict = heat_scale == "max"
    wardrobe_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "HEAT_SEX_WARDROBE_DRESSED",
            "HEAT_SEX_WARDROBE_WEAK",
            "HEAT_UNDRESS_BEAT_MISSING",
            "HEAT_WARDROBE_RE_DRESS",
            "HEAT_WARDROBE_TEXT_CONFLICT",
        }
    ]
    if sex_wardrobe_strict is True and wardrobe_fail_codes:
        raise FilmSpecError(
            "sex wardrobe ladder failed (sex_wardrobe_strict): "
            + ",".join(wardrobe_fail_codes)
            + " — act/climax must set wardrobe_state=partial|undressed|bare "
            "(or dsl bare skin / armor off / 半裸 / 卸甲); include undress beat; "
            "后镜必须延续前镜卸装状态、禁止回穿；"
            "下一镜 start_pose/subject 从已脱状态开场，禁 full wardrobe。"
            " See lessons-2026-07-21-sex-undress-ladder.md"
        )
    # VO 荤梗：实打实办事剧，旁白全程要荤；act/climax 要办事动词
    sex_vo_strict = spec.get("sex_vo_strict")
    if sex_vo_strict is None:
        sex_vo_strict = heat_scale == "max"
    vo_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "HEAT_VO_SPICE_MISSING",
            "HEAT_VO_SEX_VERB_WEAK",
            "HEAT_VO_SPICE_RATIO_LOW",
            "HEAT_VO_SPICE_TOO_MILD",
        }
    ]
    if sex_vo_strict is True and vo_fail_codes:
        raise FilmSpecError(
            "sex VO spice failed (sex_vo_strict): "
            + ",".join(vo_fail_codes)
            + " — every nar needs 荤梗; act/climax need 沉腰/办穿/吃进/锁腰/高潮… "
            "extreme 档禁纯双关。See lessons-2026-07-21-sex-vo-spice.md"
        )

    # Coitus six-beat + mute-frame pose (hard on hardcore / enabled grammar / max)
    _hardcore_profiles = {"hardcore_male", "hardcore", "重口男向"}
    coitus_strict = spec.get("coitus_strict")
    if coitus_strict is None:
        ap = str(audience_profile or "").strip().lower()
        coitus_strict = ap in _hardcore_profiles or bool(
            (coitus_grammar or {}).get("enabled") is True
        )
    coitus_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "COITUS_BEAT_MISSING",
            "COITUS_UNREADABLE_POSE",
            "COITUS_PSEUDO_SEX",
        }
    ]
    if coitus_strict is True and coitus_fail_codes:
        raise FilmSpecError(
            "coitus grammar failed (coitus_strict): "
            + ",".join(coitus_fail_codes)
            + " — assign coitus_beat entry→hook; act stills must be coitus-readable "
            "(straddle/hips-sink/grind), not hug-only. See intercourse-impact-benchmark."
        )

    size_ladder_strict = spec.get("size_ladder_strict")
    if size_ladder_strict is None:
        size_ladder_strict = str(audience_profile or "").strip().lower() in _hardcore_profiles
    size_fail_codes = [c for c in (heat_rep.get("codes") or []) if str(c).startswith("SIZE_")]
    if size_ladder_strict is True and size_fail_codes:
        raise FilmSpecError(
            "size ladder failed (size_ladder_strict): "
            + ",".join(size_fail_codes)
            + " — vary WS→MS→CU→insert; do not reopen wide mid-act. "
            "See size-ladder-hardcore-stack."
        )

    montage_strict = spec.get("montage_strict")
    if montage_strict is None:
        montage_strict = str(audience_profile or "").strip().lower() in _hardcore_profiles
    montage_fail = [c for c in (heat_rep.get("codes") or []) if str(c).startswith("MONTAGE_")]
    if montage_strict is True and montage_fail:
        raise FilmSpecError(
            "montage craft failed (montage_strict): "
            + ",".join(montage_fail)
            + " — need insert/smash/montage variety. See montage-hardcore-male."
        )

    pose_strict = spec.get("pose_strict")
    if pose_strict is None:
        pose_strict = str(audience_profile or "").strip().lower() in _hardcore_profiles
    if pose_strict is True and "SEX_POSE_STALE" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "sex pose variety failed (pose_strict): SEX_POSE_STALE — "
            "rotate sex_pose across act shots (straddle/cowgirl/from_behind…)."
        )

    vo_motion_strict = spec.get("sex_vo_motion_strict")
    if vo_motion_strict is None:
        vo_motion_strict = str(audience_profile or "").strip().lower() in _hardcore_profiles
    if vo_motion_strict is True and "HEAT_VO_MOTION_MISMATCH" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "vo-motion align failed (sex_vo_motion_strict): HEAT_VO_MOTION_MISMATCH — "
            "mirror nar sex verbs in dsl.action/motion."
        )

    # Heroine cast mode: single (default) vs multi — elastic from prompt/images/fields
    cast_ids: list[str] = []
    heroine_ids: list[str] = []
    raw_cast = intent.get("cast") if isinstance(intent.get("cast"), list) else None
    if raw_cast:
        cast_ids = [str(x).strip() for x in raw_cast if str(x).strip()]
    if isinstance(spec.get("cast_ids"), list):
        cast_ids = cast_ids or [str(x).strip() for x in spec["cast_ids"] if str(x).strip()]
    if isinstance(spec.get("heroine_ids"), list):
        heroine_ids = [str(x).strip() for x in spec["heroine_ids"] if str(x).strip()]
    elif isinstance(intent.get("heroines"), list):
        heroine_ids = [str(x).strip() for x in intent["heroines"] if str(x).strip()]

    cast_masters: dict[str, Any] = {}
    if isinstance(spec.get("cast_masters"), dict):
        cast_masters = dict(spec["cast_masters"])
    # optional style-bible path not always present; agent may put masters on spec

    # Female ref images: explicit list or count from user uploads
    female_ref_n: int | None = None
    if isinstance(spec.get("female_ref_image_count"), (int, float)):
        female_ref_n = int(spec["female_ref_image_count"])
    elif isinstance(spec.get("cast_ref_images"), list):
        female_ref_n = len([x for x in spec["cast_ref_images"] if x])
    elif isinstance(intent.get("cast_ref_images"), list):
        female_ref_n = len([x for x in intent["cast_ref_images"] if x])

    prompt_blob = " ".join(
        str(x or "")
        for x in (
            intent.get("tone"),
            intent.get("logline"),
            intent.get("theme"),
            spec.get("title"),
            spec.get("description"),
            spec.get("user_prompt"),
            spec.get("brief"),
        )
    )
    resolved = resolve_heroine_cast_mode(
        multi_heroine=spec.get("multi_heroine"),
        cast_mode=spec.get("cast_mode"),
        heroine_ids=heroine_ids,
        cast_ids=cast_ids,
        cast_masters=cast_masters,
        prompt_blob=prompt_blob,
        female_ref_image_count=female_ref_n,
    )
    # Persist resolved mode; do not invent multi_heroine when single
    # Keep cast_mode as resolved only if author used auto/omit
    author_mode = str(spec.get("cast_mode") or "auto").strip().lower()
    if author_mode in {"", "auto"}:
        spec["cast_mode"] = resolved["mode"]
    if resolved["active"]:
        if spec.get("multi_heroine") is None:
            spec["multi_heroine"] = True
        if resolved.get("heroine_ids") and not heroine_ids:
            spec["heroine_ids"] = list(resolved["heroine_ids"])
    # leave multi_heroine unset/false as author wrote — don't force false rewrite

    mh = lint_multi_heroine(
        shots,
        cast_ids=cast_ids,
        heroine_ids=list(resolved.get("heroine_ids") or heroine_ids),
        active=bool(resolved.get("active")),
        cast_mode=str(resolved.get("mode") or "single"),
    )
    mh = {
        **mh,
        "resolved": resolved,
        "cast_mode": resolved.get("mode"),
        "active": resolved.get("active"),
    }
    spec["_multi_heroine"] = mh
    notes = list(spec.get("_cast_mode_notes") or [])
    notes.append(f"cast_mode={resolved.get('mode')} reasons={resolved.get('reasons')}")
    spec["_cast_mode_notes"] = notes
    if spec.get("multi_heroine_strict") is True and mh["warning_count"] > 0:
        raise FilmSpecError(
            "multi-heroine lint failed (multi_heroine_strict): "
            + ",".join(mh["codes"] or ["MULTI"])
        )

    return shots
