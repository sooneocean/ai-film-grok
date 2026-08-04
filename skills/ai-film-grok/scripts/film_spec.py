#!/usr/bin/env python3
"""Strict film-spec validation shared by control-plane and renderer."""

from __future__ import annotations

import contextlib
import re
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
    lint_production_consistency,
    lint_transition_styles,
    lint_vo_motion_link,
)
from continuity_chain import (
    is_long_form,
)
from dialogue_broll import DialogueBrollError, iter_dialogue_broll, validate_dialogue_broll
from dialogue_contracts import summarize_dialogue_contracts
from edit_policy import (
    _CRAFT_WHY,
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    apply_coverage_defaults_to_shot,
    apply_heat_phase_defaults,
    apply_wardrobe_continuity,
    compute_erotic_impact_score,
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
from framing_lint import lint_composition_rules, lint_framing_iron, lint_vertical_safe_area
from narrative_timeline import (
    NarrativeTimelineError,
    validate_linear_narration,
    validate_sfx_scene_bindings,
)
from rhythm import lint_rhythm
from security_policy import SecurityPolicyError, validate_identifier
from sound_plan import (
    SoundPlanError,
    default_sound_plan_for_film,
    inject_auto_sfx_if_empty,
    inject_music_energy_spotting,
    inject_sex_sfx_from_shots,
    resolve_sidechain,
    validate_sound_plan,
)
from transition_ops import TransitionOperationError, build_transition_operations

VO_MODES = frozenset({"storyteller", "character", "hybrid", "dialogue_drama"})
MAX_ON_CAMERA_DIALOGUE_CHARS = 42
ON_CAMERA_SHOT_SIZES = frozenset({"medium close-up", "close-up", "extreme close-up", "ecu"})
TTS_BACKENDS = frozenset(
    {
        "audio_node",
        "auto",
        "mimo",
        "minimax",
        "fish",
        "voicebox",
        "edge",
        "external",
        "grok",
        "cosyvoice-local",
        "kokoro-local",
        "chatterbox-local",
        "piper-local",
    }
)
# Motion provider profile. FRW LTX 2.3 is the production action primary.
# ``seedance_first`` and ``grok_primary`` remain readable compatibility inputs.
I2V_PROVIDERS = frozenset({"frw", "frw-ltx23", "grok", "comfy-h3", "auto"})
I2V_PROFILES = frozenset({"ltx23_primary", "seedance_first", "grok_primary", "hybrid_h3"})
# Native resolution for 9:16 shorts. FRW LTX may return 704x1280 and must
# preserve that native pair; conforming is a later delivery decision.
DEFAULT_FRW_ASPECT = "9:16"
DEFAULT_FRW_RESOLUTION = "720p"
DEFAULT_FRW_DURATION = "5"
DEFAULT_FRW_FPS = "24"
# LTX preferred pixel size for vertical shorts (probe-validated 2026-07-20)
DEFAULT_LTX_WIDTH = "704"
DEFAULT_LTX_HEIGHT = "1280"
# Explicit legacy FRW lifeboat; it is not part of the automatic action chain.
FRW_I2V_FRW_ONLY_LIFEBOAT = "legacy-img2video"
ACTION_MOTION_PROVIDER_CHAIN = (
    "frw_ltx23_img2video_audio",
    "frw_api_img2video",
    "grok_video_1_5",
)
# Env / synth layer (no face import): LTX T2V is primary for B-roll beds
# 2026-07-21: ltx-t2v completed on sample key; seedance t2v may 403
DEFAULT_FRW_ENV_MODEL = "ltx-t2v"
# FRW video model keys (frwclaw NEW_VIDEO_TEMPLATES + legacy)
# NEVER default legacy img2video (胃镜室质量坑).
FRW_VIDEO_MODELS = frozenset(
    {
        "seedance-2-fast-i2v",  # retained solely to give old specs a clear unavailable error
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

    ``seedance_first`` is retained for backwards-compatible parsing but now
    normalizes to the supported Grok-first action chain.
    """
    from config_loader import get_config

    cfg = get_config()
    raw = cfg.i2v_profile.strip().lower()
    if raw == "seedance_first":
        return "grok_primary"
    return raw if raw in I2V_PROFILES else "grok_primary"


def default_i2v_provider() -> str:
    profile = resolve_i2v_profile()
    if profile in {"grok_primary", "hybrid_h3"}:
        # hybrid_h3 keeps Grok as the bulk auto lock; restricted shots route to
        # comfy-h3 via production_router / shot intent, not a film-wide lock.
        return "grok"
    return "frw-ltx23" if profile == "ltx23_primary" else "frw"


# H3 ships stereo diegetic audio; prefer keeping it when usable.
# strip_native_use_tts_bgm remains available when VO-only plates are wanted.
H3_AUDIO_POLICIES = frozenset(
    {
        "prefer_native",  # default: keep if usable, else strip for TTS/BGM
        "keep_native",  # always keep H3 native track
        "strip_native_use_tts_bgm",
        "mute_native",
    }
)

DEFAULT_H3_CONFIG: dict[str, object] = {
    "enabled": False,
    "stage": "pilot",
    "max_duration_sec": 8,
    "megapixels_draft": 0.2,
    "megapixels_select": 0.6,
    "audio_policy": "prefer_native",
    "allow_bulk": False,
}


def resolve_h3_config(spec: dict | None = None) -> dict[str, object]:
    """Merge film-spec h3 block with profile defaults (hybrid_h3 opts in).

    Adult / heat max films auto-enable dual-lane H3 (Grok bulk + local meat)
    unless ``h3.enabled`` is explicitly false or heat is soft.
    """
    profile = resolve_i2v_profile()
    raw = (spec or {}).get("h3") if isinstance(spec, dict) else None
    merged = dict(DEFAULT_H3_CONFIG)
    if profile == "hybrid_h3":
        merged["enabled"] = True
    # Adult-max default dual-lane without requiring env hybrid_h3.
    if isinstance(spec, dict) and profile != "ltx23_primary":
        genre = str(spec.get("genre") or "").strip().lower()
        heat = str(spec.get("heat_scale") or "").strip().lower()
        adult_max = spec.get("adult_max_iron")
        soft = heat in {"soft", "medium"} or adult_max is False
        adultish = genre == "adult" or heat in {"max", "hot", "extreme"}
        explicit_enabled = raw.get("enabled") if isinstance(raw, dict) else None
        if (
            not soft
            and adultish
            and explicit_enabled is not False
            and (explicit_enabled is True or not isinstance(raw, dict) or "enabled" not in raw)
        ):
            merged["enabled"] = True
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in DEFAULT_H3_CONFIG or key in {"notes"}:
                merged[key] = value
        if raw.get("enabled") is False:
            merged["enabled"] = False
    # clamp duration hard top for GPU safety
    try:
        max_dur = float(merged.get("max_duration_sec") or 8)
    except (TypeError, ValueError):
        max_dur = 8.0
    merged["max_duration_sec"] = max(3.0, min(max_dur, 15.0))
    try:
        mp = float(merged.get("megapixels_draft") or 0.2)
    except (TypeError, ValueError):
        mp = 0.2
    merged["megapixels_draft"] = max(0.1, min(mp, 1.0))
    audio = str(merged.get("audio_policy") or "prefer_native").strip()
    if audio not in H3_AUDIO_POLICIES:
        audio = "prefer_native"
    merged["audio_policy"] = audio
    return merged


def default_frw_video_model() -> str:
    return FRW_I2V_FRW_ONLY_LIFEBOAT


def frw_i2v_fallback_chain() -> tuple[str, ...]:
    return (
        "frw:img2video-api",
        "grok:video-1.5",
    )


# Back-compat names used across codebase
DEFAULT_I2V_PROVIDER = "auto"  # resolved in validate via profile
DEFAULT_FRW_VIDEO_MODEL = FRW_I2V_FRW_ONLY_LIFEBOAT
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
        voice_lang = str(voice.get("language") or "").lower()
        if voice_lang not in {"zh", "ja"}:
            raise FilmSpecError(
                f"{shot_id}: character dialogue voice language must be zh (default) or ja (opt-in)"
            )
        if voice_lang == "ja":
            if str(shot.get("translation_status") or "").lower() != "ready":
                raise FilmSpecError(
                    f"{shot_id}: Japanese dialogue translation is pending; "
                    "fill dialogue_ja before TTS/lipsync"
                )
            if not re.search(r"[\u3040-\u30ff]", str(shot.get("dialogue_ja") or "")):
                raise FilmSpecError(f"{shot_id}: dialogue_ja must contain Japanese kana")
        else:
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


def validate_film_spec(
    spec: dict[str, Any],
    *,
    assign_missing_ids: bool,
    film_root: Any | None = None,
    enforce_narrative_timeline: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(spec, dict):
        raise FilmSpecError("film-spec must be a JSON object")
    _required_text(spec.get("title"), field="title")
    mode = _required_text(spec.get("vo_mode"), field="vo_mode").lower()
    if mode not in VO_MODES:
        raise FilmSpecError(f"film-spec vo_mode must be one of {sorted(VO_MODES)}")
    spec["vo_mode"] = mode
    if mode != "dialogue_drama" and iter_dialogue_broll(spec):
        raise FilmSpecError("dialogue_broll is only supported when vo_mode=dialogue_drama")
    if mode == "dialogue_drama":
        dlang = str(spec.get("dialogue_spoken_lang") or "zh").lower()
        if dlang not in {"zh", "ja"}:
            raise FilmSpecError(
                "dialogue_drama requires dialogue_spoken_lang=zh (default) or ja (opt-in)"
            )
        spec["dialogue_spoken_lang"] = dlang
        if str(spec.get("narration_spoken_lang") or "zh").lower() != "zh":
            raise FilmSpecError("dialogue_drama requires narration_spoken_lang=zh")
        spec["narration_spoken_lang"] = "zh"
        if not str(spec.get("caption_lang") or "").strip():
            spec["caption_lang"] = "zh"
    validate_director_intent(spec)
    if mode == "dialogue_drama":
        # v2.34 dialogue-first scene contract gate (early): every scene must put a
        # speaking character in frame at least once (on_camera/off_camera dialogue cue
        # with non-empty spoken_text). Scenes that only carry silence, coverage or
        # pure narration VO are rejected — narration stays gap-only, never the
        # primary voice of a scene. Escapes: scene {"silent_scene": true,
        # "narration_reason": "..."} for a justified gap scene, or spec-level
        # allow_silent_scenes:true.
        allow_silent_scenes_early = spec.get("allow_silent_scenes") is True
        scenes_early = spec.get("scenes")
        if not allow_silent_scenes_early and isinstance(scenes_early, list) and scenes_early:
            scenes_without_dialogue_early: list[str] = []
            for scene_index, scene in enumerate(scenes_early, start=1):
                if not isinstance(scene, dict):
                    continue
                if scene.get("silent_scene") is True:
                    if not str(scene.get("narration_reason") or "").strip():
                        scenes_without_dialogue_early.append(
                            f"scene{scene_index}(id={scene.get('id') or scene_index}):"
                            f"silent_scene_requires_narration_reason"
                        )
                    continue
                scene_shots = scene.get("shots")
                if not isinstance(scene_shots, list):
                    continue
                has_dialogue = False
                for scene_shot in scene_shots:
                    if not isinstance(scene_shot, dict):
                        continue
                    if str(scene_shot.get("screen_mode") or "") not in {
                        "on_camera",
                        "off_camera",
                    }:
                        continue
                    cues = scene_shot.get("audio_cues")
                    if not isinstance(cues, list):
                        continue
                    if any(
                        isinstance(cue, dict)
                        and cue.get("kind") == "voice"
                        and cue.get("line_type") == "dialogue"
                        and str(cue.get("spoken_text") or "").strip()
                        for cue in cues
                    ):
                        has_dialogue = True
                        break
                if not has_dialogue:
                    scenes_without_dialogue_early.append(
                        f"scene{scene_index}(id={scene.get('id') or scene_index})"
                    )
            if scenes_without_dialogue_early:
                raise FilmSpecError(
                    "dialogue_drama requires dialogue in every scene — no narration-only "
                    "or silence-only scenes: "
                    + "; ".join(scenes_without_dialogue_early)
                    + ". Give the scene at least one on_camera/off_camera character "
                    "dialogue cue with visible speaking character. Escapes: scene "
                    "{'silent_scene': true, 'narration_reason': '...'} for a justified "
                    "gap scene, or spec-level allow_silent_scenes:true."
                )
    tts_backend = spec.get("tts_backend", "auto")
    if not isinstance(tts_backend, str) or tts_backend.lower() not in TTS_BACKENDS:
        raise FilmSpecError(f"film-spec tts_backend must be one of {sorted(TTS_BACKENDS)}")
    spec["tts_backend"] = tts_backend.lower()
    # 中文说书默认钉 MiMo；缺 key 时显式失败，避免静默换声线或 provider。
    if mode in ("storyteller", "hybrid") and spec["tts_backend"] == "auto":
        spec["tts_backend"] = "mimo"
        notes = list(spec.get("_tts_notes") or [])
        notes.append("auto→mimo for storyteller/hybrid (中文说书默认；显式 edge/fish/… 可覆盖)")
        spec["_tts_notes"] = notes
    # I2V profile is explicit so existing projects can keep their locked route.
    i2v_profile = resolve_i2v_profile()
    spec["_i2v_profile"] = i2v_profile
    chain = frw_i2v_fallback_chain()
    raw_i2v = spec.get("i2v_provider", "auto")
    spec["_i2v_provider_explicit"] = isinstance(raw_i2v, str) and raw_i2v.strip().lower() != "auto"
    raw_still = spec.get("still_provider", "auto")
    if not isinstance(raw_still, str) or raw_still.lower() not in {
        "auto",
        "comfy_lan",
        "grok",
    }:
        raise FilmSpecError("film-spec still_provider must be one of ['auto', 'comfy_lan', 'grok']")
    spec["still_provider"] = raw_still.lower()
    if not isinstance(raw_i2v, str) or raw_i2v.lower() not in I2V_PROVIDERS:
        raise FilmSpecError(f"film-spec i2v_provider must be one of {sorted(I2V_PROVIDERS)}")
    i2v_provider = raw_i2v.lower()
    if i2v_provider == "auto":
        i2v_provider = default_i2v_provider()
        i2v_notes = list(spec.get("_i2v_notes") or [])
        if i2v_profile == "ltx23_primary":
            i2v_notes.append(
                "auto→frw-ltx23 (LTX 2.3 native-audio primary; fresh approved canary and "
                "per-shot media review required)"
            )
        elif i2v_profile == "grok_primary":
            i2v_notes.append(
                "auto→grok (AIFILM_I2V_PROFILE=grok_primary / Seedance unavailable: "
                "bulk image_to_video; still=image_edit cast; register image_to_video)"
            )
        elif i2v_profile == "hybrid_h3":
            i2v_notes.append(
                "auto→grok bulk primary + hybrid_h3 lanes: restricted/meat → comfy-h3 pilot; "
                "env → FRW ltx-t2v; dialogue → FRW LTX; setup non-sensitive → Grok; "
                "H3 audio prefer_native (keep usable stereo; else strip→TTS/BGM)"
            )
        else:
            i2v_notes.append("auto→frw-ltx23 (compatibility profile normalized to LTX primary)")
        spec["_i2v_notes"] = i2v_notes
    # Explicit legacy FRW remains readable for a deliberate recovery run.
    if i2v_profile in {"grok_primary", "hybrid_h3"} and i2v_provider == "frw":
        i2v_notes = list(spec.get("_i2v_notes") or [])
        i2v_notes.append(
            "NOTE explicit i2v_provider=frw — allowed only for a recorded technical fallback; "
            "auto always resolves to Grok primary"
        )
        spec["_i2v_notes"] = i2v_notes
    spec["i2v_provider"] = i2v_provider
    # Dual-lane MiniMax H3: hybrid_h3 profile, explicit h3.enabled, or adult-max auto.
    h3_cfg = resolve_h3_config(spec)
    spec["h3"] = h3_cfg
    if h3_cfg.get("enabled") is True:
        if str(spec.get("_i2v_profile") or "") == "grok_primary":
            spec["_i2v_profile"] = "hybrid_h3"
            notes = list(spec.get("_i2v_notes") or [])
            notes.append(
                "adult/heat dual-lane: film promoted to hybrid_h3 (Grok setup bulk + "
                "local MiniMax H3 restricted/meat); set h3.enabled=false to opt out"
            )
            spec["_i2v_notes"] = notes
        if not isinstance(spec.get("motion_lanes"), dict):
            spec["motion_lanes"] = {
                "default": "cloud",
                "restricted_local": "comfy-h3",
                "env": "frw_ltx_t2v",
                "dialogue": "frw_ltx23",
                "setup_non_sensitive": "grok",
            }
    # FRW video model (Seedance/LTX path). auto → seedance id kept as aspirational label
    raw_fvm = spec.get("frw_video_model", default_frw_video_model())
    if not isinstance(raw_fvm, str) or raw_fvm.lower() not in FRW_VIDEO_MODELS:
        raise FilmSpecError(f"film-spec frw_video_model must be one of {sorted(FRW_VIDEO_MODELS)}")
    fvm = raw_fvm.lower()
    if i2v_provider == "frw-ltx23" and fvm == "legacy-img2video":
        fvm = "ltx-i2v"
    if fvm == "seedance-2-fast-i2v":
        raise FilmSpecError(
            "frw_video_model=seedance-2-fast-i2v is unavailable; use LTX 2.3 Audio or "
            "legacy-img2video only as the reviewed FRW fallback"
        )
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
            "FRW API img2video fallback: current film canary plus decoded, human-approved "
            "media are required; register frw_img2video with the actual returned model; "
            "prefer the LTX → FRW API I2V → Grok Video 1.5 chain"
        )
        spec["_frw_video_notes"] = notes
    if fvm.startswith("ltx-"):
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            "LTX: width/height/duration/fps must be strings; "
            "9:16 preserve native 704×1280; do not upscale or stretch; "
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
        # FRW fallback may use a provider resolution label, but native LTX
        # pixels remain 704x1280 for vertical generation.
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
    # Action fallback order is policy, while execution remains capability- and
    # receipt-gated in i2v_provider.generate_with_fallback.
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
    hero_primary = (
        "frw_ltx23_img2video_audio"
        if i2v_provider == "frw-ltx23"
        else "grok_image_to_video"
        if i2v_provider == "grok"
        else f"frw:{fvm}"
    )
    spec["_layer_routing"] = {
        "i2v_profile": i2v_profile,
        "hero_still": "grok_image_edit_cast",
        "hero_motion_primary": hero_primary,
        "hero_i2v_provider": i2v_provider,
        "hero_motion_priority": list(ACTION_MOTION_PROVIDER_CHAIN),
        "hero_motion_fallback": list(chain),
        "hero_motion_frw_only_lifeboat": FRW_I2V_FRW_ONLY_LIFEBOAT,
        "env_synth_primary": "frw_ltx_t2v",
        "env_synth_fallback": [
            "grok:image_to_video_no_face",
            "local:verified-t2v",
        ],
        "env_plate_cli": "frw newvideo --model ltx-t2v; then Grok no-face I2V if unavailable",
        "env_register_endpoint": "frw_ltx_t2v",
        "key_canary": (
            "FRW LTX, FRW API I2V, and Grok Video 1.5 each need a film-scoped approved "
            "canary before fallback"
        ),
        "register_endpoint_hero": (
            "frw_ltx23_img2video_audio"
            if i2v_provider == "frw-ltx23"
            else "image_to_video"
            if i2v_provider == "grok"
            else "frw_seedance_i2v|frw_ltx_*|frw_img2video"
        ),
        "designed_post": "hyperframes|remotion",
        "note": (
            "action order is FRW LTX 2.3 → Grok I2V → verified FRW Wan → other verified "
            "local I2V; unready providers are skipped, while an attempted provider switches "
            "only after a classified technical failure"
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
    native_volume = spec.get("native_audio_volume", 0.72)
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
    _vo_lint_violations: list[dict[str, Any]] = []  # P2-10: collected for vo_lint_strict
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
            if shot.get("dialogue_broll") is not None:
                try:
                    validate_dialogue_broll(shot, shot_id=shot_id)
                except DialogueBrollError as exc:
                    raise FilmSpecError(str(exc)) from exc
            if mode == "dialogue_drama":
                _validate_dialogue_drama_shot(
                    shot,
                    shot_id=shot_id,
                    narration_gap_strict=spec.get("narration_gap_strict") is True,
                )
                nar = shot.get("nar")
                if nar is not None:
                    shot["nar"] = validate_nar_budget(nar, field=f"{shot_id}.nar")
                else:
                    shot["est_vo_sec"] = 0.0
            else:
                shot["nar"] = validate_nar_budget(shot.get("nar"), field=f"{shot_id}.nar")
            # v1.23: VO script lint — brochure phrase / AI-cadence / long-sentence warnings.
            # Advisory only (warnings); genre=product can elevate to hard gate.
            from vo_lint import lint_nar_text

            _vo_warnings = lint_nar_text(str(shot.get("nar") or ""), shot_id=shot_id)
            if _vo_warnings:
                shot.setdefault("_vo_lint_warnings", [w.to_dict() for w in _vo_warnings])
                for w in _vo_warnings:
                    _vo_lint_violations.append({"shot_id": shot_id, **w.to_dict()})
            elif "_vo_lint_warnings" in shot:
                del shot["_vo_lint_warnings"]
            # Optional English line for dual captions (designed-post); not TTS-spoken by default
            nar_en = shot.get("nar_en")
            if nar_en is not None:
                if not isinstance(nar_en, str):
                    raise FilmSpecError(f"{shot_id}.nar_en must be a string")
                shot["nar_en"] = nar_en.strip()
            shot["est_vo_sec"] = estimate_nar_vo_sec(str(shot.get("nar") or ""))
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
            if mode == "dialogue_drama" and shot.get("screen_mode") == "on_camera":
                shot.setdefault("dialogue_motion_route", "auto")
                shot["_recommended_engine"] = {
                    "state_still": "comfy_qwen_i2i_performance_state",
                    "keyframe": "comfy_qwen_i2i_from_performance_state",
                    "motion": "frw_ltx23_img2video_audio",
                    "motion_primary": "frw_ltx23_img2video_audio",
                    "motion_fallback": "frw_img2video_rejection_only",
                    "lipsync_primary": "frw_ltx23_native_audio_i2v_human_verified",
                    "lipsync_fallback": "rtx_latentsync_1_6_after_frw_img2video_fallback",
                    "fallback_trigger": "reviewed_ltx_native_audio_rejection_only",
                    "native_text_gate": "reject_provider_burned_text_before_post",
                    "forbid": [
                        "quality_rejection_as_provider_fallback",
                        "unreviewed_lipsync",
                        "provider_burned_text",
                        "full_cast_reference_when_state_photo_exists",
                        "experimental_whole_frame_talking_as_default",
                    ],
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

    # P2-10: vo_lint_strict — product genre or explicit flag elevates VO de-AI lint to hard
    if spec.get("vo_lint_strict") is True and _vo_lint_violations:
        codes = sorted({v.get("code", "VO_LINT") for v in _vo_lint_violations})
        raise FilmSpecError("vo_lint failed (vo_lint_strict): " + ",".join(codes))
    spec["_vo_lint_summary"] = {
        "ok": len(_vo_lint_violations) == 0,
        "violation_count": len(_vo_lint_violations),
        "violations": _vo_lint_violations,
        "note": "VO de-AI lint: brochure phrase / AI cadence / long sentence. "
        "Soft by default; vo_lint_strict raises.",
    }

    if mode == "dialogue_drama":
        on_camera = [s for s in shots if s.get("screen_mode") == "on_camera"]
        coverage = [
            s for s in shots if s.get("screen_mode") in {"reaction", "action_cover", "silence"}
        ]
        if len(on_camera) >= 2 and not coverage:
            raise FilmSpecError(
                "dialogue_drama requires a reaction/action_cover/silence shot; "
                "do not cut consecutive speaking close-ups only"
            )
        coverage_beats = {
            str(shot.get("beat_id") or "")
            for shot in coverage
            if str(shot.get("beat_id") or "").strip()
        }
        # Timed dialogue B-roll is coverage beneath its parent A-roll: it
        # replaces picture while retaining that line's dialogue/caption clock.
        # Treat it as beat coverage as well as legacy standalone cover shots.
        coverage_beats.update(
            str(shot.get("beat_id") or "")
            for shot in on_camera
            if shot.get("dialogue_broll") and str(shot.get("beat_id") or "").strip()
        )
        missing_beat_coverage = sorted(
            {
                str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "")
                for shot in on_camera
                if str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "")
                not in coverage_beats
            }
        )
        if missing_beat_coverage:
            raise FilmSpecError(
                "dialogue_drama requires reaction/action_cover/silence for every dialogue beat; "
                "missing=" + ",".join(missing_beat_coverage)
            )
        # Dialogue-first scene contract: every scene must put a speaking character
        # in frame at least once (on_camera or off_camera dialogue). Scenes made of
        # pure silence/coverage plates or narration-VO-only pictures are rejected —
        # narration is gap-only, never the primary voice of a scene.
        # Escape: scene {"silent_scene": true, "narration_reason": "..."} or spec-level
        # allow_silent_scenes:true.
        allow_silent_scenes = spec.get("allow_silent_scenes") is True
        has_scenes = isinstance(spec.get("scenes"), list) and bool(spec.get("scenes"))

        def _scene_dialogue_shots(scene: dict[str, Any]) -> list[dict[str, Any]]:
            scene_shots = scene.get("shots")
            if not isinstance(scene_shots, list):
                return []
            talking: list[dict[str, Any]] = []
            for scene_shot in scene_shots:
                if not isinstance(scene_shot, dict):
                    continue
                if str(scene_shot.get("screen_mode") or "") not in {"on_camera", "off_camera"}:
                    continue
                cues = scene_shot.get("audio_cues")
                if not isinstance(cues, list):
                    continue
                if any(
                    isinstance(cue, dict)
                    and cue.get("kind") == "voice"
                    and cue.get("line_type") == "dialogue"
                    and str(cue.get("spoken_text") or "").strip()
                    for cue in cues
                ):
                    talking.append(scene_shot)
            return talking

        scenes_without_dialogue: list[str] = []
        if has_scenes and not allow_silent_scenes:
            for scene_index, scene in enumerate(spec.get("scenes") or [], start=1):
                if not isinstance(scene, dict):
                    continue
                if scene.get("silent_scene") is True:
                    if str(scene.get("narration_reason") or "").strip():
                        continue
                    scenes_without_dialogue.append(
                        f"scene{scene_index}(id={scene.get('id') or scene_index}):"
                        "silent_scene_requires_narration_reason"
                    )
                    continue
                if not _scene_dialogue_shots(scene):
                    scenes_without_dialogue.append(
                        f"scene{scene_index}(id={scene.get('id') or scene_index})"
                    )
        consecutive = 0
        prior_speaker = ""
        for shot in shots:
            if shot.get("screen_mode") == "on_camera":
                speaker = str(shot.get("speaker") or "")
                consecutive = consecutive + 1 if speaker and speaker == prior_speaker else 1
                prior_speaker = speaker
                if consecutive >= 3:
                    raise FilmSpecError(
                        "dialogue_drama forbids three consecutive on_camera shots for the same speaker; "
                        "insert reaction/action_cover/silence"
                    )
            else:
                consecutive = 0
                prior_speaker = ""
        dialogue_sec = sum(
            float(cue.get("duration_sec") or 0)
            for shot in shots
            for cue in (shot.get("audio_cues") or [])
            if isinstance(cue, dict)
            and cue.get("kind") == "voice"
            and cue.get("line_type") == "dialogue"
        )
        narration_sec = sum(
            float(cue.get("duration_sec") or 0)
            for shot in shots
            for cue in (shot.get("audio_cues") or [])
            if isinstance(cue, dict)
            and cue.get("kind") == "voice"
            and cue.get("line_type") == "narration"
        )
        narration_ratio = narration_sec / max(dialogue_sec + narration_sec, 1.0)
        # Delivery Truth · zero_narration IRON (default on for dialogue_drama)
        zn = zero_narration_gate(spec, shots=shots)
        spec["_zero_narration"] = zn
        zero_strict = bool(zn.get("zero_narration_strict"))
        if zero_strict:
            narration_budget = 0.0
        else:
            try:
                narration_budget = float(spec.get("narration_budget_ratio") or 0.05)
            except (TypeError, ValueError):
                narration_budget = 0.05
            narration_budget = max(0.0, min(0.15, narration_budget))
        if not zn.get("ok"):
            raise FilmSpecError(
                f"NAR_BUDGET_VIOLATION: {zn.get('message') or 'zero narration strict failed'}"
            )
        # Legacy storyteller ban when IRON not escaped (zero_strict already covers)
        if zero_strict and spec.get("allow_storyteller_nar") is not True:
            for shot in shots:
                if not isinstance(shot, dict):
                    continue
                sid = str(shot.get("id") or "?")
                nar = str(shot.get("nar") or "").strip()
                if not nar:
                    continue
                cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
                has_dialogue_voice = any(
                    isinstance(c, dict)
                    and c.get("kind") == "voice"
                    and c.get("line_type") == "dialogue"
                    for c in cues
                ) or bool(str(shot.get("spoken_text") or "").strip())
                has_narration_voice = any(
                    isinstance(c, dict)
                    and c.get("kind") == "voice"
                    and c.get("line_type") == "narration"
                    for c in cues
                )
                if has_dialogue_voice:
                    continue
                if has_narration_voice and str(shot.get("narration_reason") or "").strip():
                    continue
                if (
                    str(shot.get("narration_reason") or "").strip()
                    and shot.get("silent_scene") is True
                ):
                    continue
                raise FilmSpecError(
                    f"NAR_BUDGET_VIOLATION: {sid}: dialogue_drama forbids third-person "
                    "storyteller nar as primary voice — use character dialogue, pure-visual "
                    "silence/action_cover, or escape zero_narration_strict:false / "
                    "allow_storyteller_nar:true"
                )
        spec["_dialogue_drama"] = {
            "on_camera_shots": len(on_camera),
            "coverage_shots": len(coverage),
            "scenes_without_dialogue": scenes_without_dialogue,
            "allow_silent_scenes": allow_silent_scenes,
            "coverage_beats": sorted(coverage_beats),
            "missing_beat_coverage": missing_beat_coverage,
            "dialogue_sec": round(dialogue_sec, 3),
            "narration_sec": round(narration_sec, 3),
            "narration_ratio": round(float(zn.get("ratio") or narration_ratio), 4),
            "narration_target_ratio": 0.0,
            "narration_budget_ratio": narration_budget,
            "zero_narration_strict": zero_strict,
            "coverage_ratio": round(
                sum(float(s.get("duration_sec") or 0) for s in coverage)
                / max(sum(float(s.get("duration_sec") or 0) for s in shots), 1.0),
                4,
            ),
            "coverage_targets": {
                "on_camera": "35-45%",
                "reaction": "20-25%",
                "action_cover": "about 20%",
                "space_or_silence": "10-15%",
            },
            "note": (
                "Cinema dialogue primary: speech=character Chinese mouth; no speech=pure picture. "
                + (
                    "Zero-narration IRON: nar hard cap 0%."
                    if zero_strict
                    else f"Narration gap-only; hard cap {narration_budget:.0%}."
                )
            ),
        }
        broll = iter_dialogue_broll(spec)
        spec["_dialogue_broll"] = {
            "enabled": bool(broll),
            "count": len(broll),
            "parent_shot_ids": [str(item.get("parent_shot_id") or "") for item in broll],
            "audio_policy": "carry_parent_dialogue",
            "note": "B-roll replaces only parent picture inside bounded cuts; dialogue/subtitle clocks stay on A-roll.",
        }
        if (
            not zero_strict
            and spec.get("narration_budget_strict") is not False
            and narration_ratio > narration_budget + 1e-9
        ):
            raise FilmSpecError(
                f"NAR_BUDGET_VIOLATION: dialogue_drama narration budget exceeded: "
                f"{narration_ratio:.0%} > {narration_budget:.0%} "
                f"(raise narration_budget_ratio or cut gap VO)"
            )

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
            sp = inject_music_energy_spotting(sp, shots, heat_scale=heat_for_sfx)
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

    # Every seam is an explicit operation, including a hard cut.  This is the
    # contract consumed by designed post and the final-delivery receipt.
    raw_ops = spec.get("transition_ops")
    if raw_ops is not None and not isinstance(raw_ops, list):
        raise FilmSpecError("transition_ops must be an array")
    try:
        resolved_intents = [str(x) for x in spec.get("transition_intents") or []]
        raw_join_secs = spec.get("join_transition_secs")
        if isinstance(raw_join_secs, list):
            operation_secs = list(raw_join_secs)
        else:
            # edit_strategy=off still receives a complete per-seam operation.
            operation_secs = [
                0.0 if intent == "hard" else float(spec["transition_sec"])
                for intent in resolved_intents
            ]
        spec["transition_ops"] = build_transition_operations(
            shots,
            crafts=[str(x) for x in spec.get("edit_craft") or []],
            intents=resolved_intents,
            styles=[str(x) for x in spec.get("transition_styles") or []],
            durations=operation_secs,
            authored=list(raw_ops) if raw_ops is not None else None,
        )
        spec["_transition_ops_source"] = "author_overlay" if raw_ops is not None else "edit_craft"
    except TransitionOperationError as exc:
        raise FilmSpecError(str(exc)) from exc

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

    # Dramatic meaning stack (shot / motion / dialogue purpose / emotional_arc).
    # Report always written; fail-closed by default (every genre pack) when
    # meaning_gate_enabled. write-spec also hard-fails via cinematic_audit
    # regardless of this flag.
    from dramatic_meaning import lint_dramatic_meaning, meaning_gate_enabled

    meaning = lint_dramatic_meaning(spec, shots=shots)
    spec["_dramatic_meaning"] = {
        "ok": meaning.get("ok"),
        "enabled": meaning_gate_enabled(spec),
        "codes": meaning.get("codes"),
        "error_count": meaning.get("error_count"),
        "issues": meaning.get("issues"),
        "parts": {
            key: {
                "ok": part.get("ok"),
                "codes": part.get("codes"),
                "error_count": part.get("error_count"),
            }
            for key, part in (meaning.get("parts") or {}).items()
            if isinstance(part, dict)
        },
        "checked": meaning.get("checked"),
        "note": meaning.get("note"),
    }
    if meaning_gate_enabled(spec) and not meaning.get("ok"):
        raise FilmSpecError(
            "dramatic meaning gate failed (dramatic_meaning_strict): "
            + ",".join(meaning.get("codes") or ["SHOT_MEANING_EMPTY"])
        )

    # Shot-local audio is additive for legacy projects, strict for new timed plans.
    try:
        from audio_cues import AudioCueError, validate_audio_cues

        spec["_audio_cues"] = validate_audio_cues(
            shots, strict=bool(spec.get("audio_cues_strict")) or mode == "dialogue_drama"
        )
    except AudioCueError as exc:
        raise FilmSpecError(str(exc)) from exc

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

    # Keep general schema/craft validation usable by authoring tools. Timeline
    # playback is enforced at write-spec and render boundaries, where every VO
    # line is actually committed to production.
    if enforce_narrative_timeline:
        try:
            validate_linear_narration(
                shots,
                vo_mode=str(spec["vo_mode"]),
                dialogue_spoken_lang=str(
                    spec.get("dialogue_spoken_lang")
                    or (spec.get("voice_policy") or {}).get("dialogue_spoken_lang")
                    or "ja"
                ),
                narration_spoken_lang=str(
                    spec.get("narration_spoken_lang")
                    or (spec.get("voice_policy") or {}).get("narration_spoken_lang")
                    or "zh"
                ),
            )
            validate_sfx_scene_bindings(spec.get("sound_plan"), shots)
        except NarrativeTimelineError as exc:
            raise FilmSpecError(f"narrative timeline invalid: {exc}") from exc
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

    # A clipped head is never a deliverable state, so this is not opt-in.
    frm = lint_framing_iron(shots)
    spec["_framing_lint"] = {
        "ok": frm["ok"],
        "codes": frm["codes"],
        "warning_count": frm["warning_count"],
        "error_count": frm["error_count"],
        "issues": frm["issues"],
        "note": frm.get("note"),
    }
    if not frm["ok"]:
        raise FilmSpecError(
            "framing iron lint failed (full head + headroom required): "
            + ",".join(frm["codes"] or ["HEAD_CROP"])
        )

    # Production consistency P2-2~P2-6 (wardrobe/hair/makeup/light/rhythm/lipsync/voice drift)
    # Soft by default; production_consistency_strict raises. bible=spec so cast_locks/
    # hair_swatches/makeup/wardrobe_variants on spec (often mirrored from style-bible) are checked.
    pcr = lint_production_consistency(shots, bible=spec, spec=spec)
    spec["_production_consistency"] = {
        "ok": pcr["ok"],
        "codes": pcr["codes"],
        "warning_count": pcr["warning_count"],
        "error_count": pcr["error_count"],
        "issues": pcr["issues"],
        "note": pcr.get("note"),
    }
    if spec.get("production_consistency_strict") is True and not pcr["ok"]:
        raise FilmSpecError(
            "production consistency lint failed (production_consistency_strict): "
            + ",".join(pcr["codes"])
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

    # Composition rules P1-7 (180° axis / 30° / eyeline / size progression)
    # Soft by default; composition_strict raises.
    compr = lint_composition_rules(shots)
    spec["_composition_rules"] = {
        "ok": compr["ok"],
        "codes": compr["codes"],
        "warning_count": compr["warning_count"],
        "error_count": compr["error_count"],
        "issues": compr["issues"],
        "note": compr.get("note"),
    }
    if spec.get("composition_strict") is True and not compr["ok"]:
        raise FilmSpecError(
            "composition rules lint failed (composition_strict): " + ",".join(compr["codes"])
        )

    # Dialogue contract P1-8 (timing/origin/lipsync truth)
    # Each shot may carry dialogue_contracts[]; validate each and collect errors.
    # Soft by default; dialogue_contract_strict raises.
    dialogue_contracts = summarize_dialogue_contracts(shots)
    spec["_dialogue_contracts"] = {
        **dialogue_contracts,
        "note": "P1-8: dialogue timing window, audio origin, lipsync truth. Soft by default.",
    }
    if spec.get("dialogue_contract_strict") is True and dialogue_contracts["errors"]:
        codes = dialogue_contracts["codes"]
        raise FilmSpecError(
            "dialogue contract validation failed (dialogue_contract_strict): " + ",".join(codes)
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
        or wardrobe_cont.get("escalated")
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
        esc = wardrobe_cont.get("escalated") or []
        if esc:
            bits.append(
                "wardrobe IRON escalate: "
                + ",".join(
                    f"{e.get('id')}:{e.get('from')}→{e.get('to')}"
                    for e in esc[:12]
                    if isinstance(e, dict)
                )
            )
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
    # max IRON: heat_arc_strict defaults true (intimacy ≥70% / setup ≤20%)
    heat_arc_strict = spec.get("heat_arc_strict")
    if heat_arc_strict is None:
        heat_arc_strict = heat_scale == "max" and spec.get("adult_max_iron") is not False
    arc_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "HEAT_INTIMACY_RATIO_LOW",
            "HEAT_SETUP_RATIO_HIGH",
            "HEAT_ACT_CLIMAX_EMPTY",
            "HEAT_ESCALATION_REGRESSION",
            "HEAT_ESCALATION_STALL",
            "HEAT_ESCALATION_NO_PEAK",
        }
    ]
    if heat_arc_strict is True and arc_fail_codes:
        raise FilmSpecError(
            "heat arc IRON failed (heat_arc_strict): "
            + ",".join(arc_fail_codes)
            + " — max: intimacy ≥60%, setup ≤20%, continuous challenge to climax bare "
            "(no mid-film cool-down / plateau). "
            "Override: heat_arc_strict:false or adult_max_iron:false."
        )
    # Explicit continuous-challenge flag (defaults with max iron)
    if spec.get("challenge_max_scale") is None and heat_scale == "max":
        if spec.get("adult_max_iron") is not False:
            spec["challenge_max_scale"] = True
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
            "raise act+climax duration_sec share to ≥50% of total (or set "
            "sex_min_duration_ratio / sex_floor_strict:false). See adult-max iron."
        )
    # Sex wardrobe IRON: undress|bare + bare peak; continuity monotonic; hard on max.
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
            "HEAT_BARE_PEAK_MISSING",
        }
    ]
    if sex_wardrobe_strict is True and wardrobe_fail_codes:
        raise FilmSpecError(
            "sex wardrobe IRON failed (sex_wardrobe_strict): "
            + ",".join(wardrobe_fail_codes)
            + " — act≥undressed, climax=bare, undress beat required; "
            "能脱就脱/能露就露；禁止回穿。See lessons-2026-07-21-sex-undress-ladder.md"
        )
    # Peak still sole-ref: undressed/bare must not restart from full cast master
    still_src_strict = spec.get("still_source_strict")
    if still_src_strict is None:
        still_src_strict = heat_scale == "max" and spec.get("adult_max_iron") is not False
    if still_src_strict is True:
        try:
            from i2v_motion_gate import lint_still_source_policy
        except Exception:  # pragma: no cover
            lint_still_source_policy = None  # type: ignore
        if lint_still_source_policy is not None:
            still_rep = lint_still_source_policy(shots)
            spec["_still_source_policy"] = still_rep
            if not still_rep.get("ok"):
                raise FilmSpecError(
                    "still source wardrobe IRON failed (still_source_strict): "
                    + ",".join(still_rep.get("codes") or [])
                    + " — peak/undressed still sole-ref must be undress-anchor or prior "
                    "undressed still; 禁 image_edit(全装 cast)。"
                    " Override: still_source_strict:false."
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
    vo_mode_now = str(spec.get("vo_mode") or "").strip().lower()
    sex_vo_auto = spec.get("sex_vo_auto_apply")
    if sex_vo_auto is None:
        sex_vo_auto = vo_mode_now != "dialogue_drama"
    # Auto-reinforce weak nar only for storyteller/hybrid (never inject third-person into dialogue_drama)
    if (
        sex_vo_strict is True
        and vo_fail_codes
        and heat_scale == "max"
        and sex_vo_auto is not False
        and vo_mode_now != "dialogue_drama"
    ):
        try:
            from edit_policy import apply_vo_spice_auto

            vo_fix = apply_vo_spice_auto(
                shots, spice_level=str(spice_level) if spice_level else "extreme"
            )
        except Exception:  # pragma: no cover
            vo_fix = {"fixed": 0, "ids": []}
        if int(vo_fix.get("fixed") or 0) > 0:
            notes = list(spec.get("_heat_notes") or [])
            notes.append(
                f"sex_vo_auto_apply fixed {vo_fix['fixed']} shots: "
                + ",".join((vo_fix.get("ids") or [])[:8])
            )
            spec["_heat_notes"] = notes
            # re-lint heat after nar rewrite
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

    # Coitus six-beat + mute-frame pose (hard on max iron / hardcore / grammar)
    _hardcore_profiles = {"hardcore_male", "hardcore", "重口男向"}
    _max_iron = heat_scale == "max" and spec.get("adult_max_iron") is not False
    coitus_strict = spec.get("coitus_strict")
    if coitus_strict is None:
        ap = str(audience_profile or "").strip().lower()
        coitus_strict = (
            _max_iron
            or ap in _hardcore_profiles
            or bool((coitus_grammar or {}).get("enabled") is True)
        )
    _coitus_hard = {
        "COITUS_BEAT_MISSING",
        "COITUS_UNREADABLE_POSE",
        "COITUS_PSEUDO_SEX",
    }
    coitus_fail_codes = [
        str(i.get("code"))
        for i in (heat_rep.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code") or "") in _coitus_hard
        and str(i.get("severity") or "") == "warning"
    ]
    if coitus_strict is True and coitus_fail_codes:
        raise FilmSpecError(
            "coitus grammar failed (coitus_strict): "
            + ",".join(sorted(set(coitus_fail_codes)))
            + " — assign coitus_beat entry→hook; act stills must be coitus-readable "
            "(straddle/hips-sink/grind), not hug-only. See intercourse-impact-benchmark."
        )

    # 肉戏起承转合 (前戏→插入→射出) hard on max iron
    # P0 · 2026-07-29: SEX_ARC_RATIO_SKEW / RELEASE_RATIO_LOW also hard-fail
    sex_arc_strict = spec.get("sex_arc_strict")
    if sex_arc_strict is None:
        sex_arc_strict = _max_iron
    sex_arc_fail = [c for c in (heat_rep.get("codes") or []) if str(c).startswith("SEX_ARC_")]
    if sex_arc_strict is True and sex_arc_fail:
        raise FilmSpecError(
            "sex arc IRON failed (sex_arc_strict): "
            + ",".join(sex_arc_fail)
            + " — 前戏→插入→射出 must all exist with penetration verbs; "
            "转拍时长≥25% 肉戏窗、合拍≥12%。"
            "禁只抱吻、禁无纳入、禁无高潮射出拍。Override: sex_arc_strict:false. "
            "See lessons-2026-07-27-adult-scale-max-sex-arc.md"
        )

    # 定器特写 hard on max
    sex_detail_cu_strict = spec.get("sex_detail_cu_strict")
    if sex_detail_cu_strict is None:
        sex_detail_cu_strict = _max_iron
    if sex_detail_cu_strict is True and "SEX_DETAIL_CU_MISSING" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "sex detail CU IRON failed (sex_detail_cu_strict): SEX_DETAIL_CU_MISSING — "
            "肉戏块至少 1 镜结合/腰腹定器特写 (coverage_role=detail 或 "
            "framing=union_closeup|genital_lock 或 close-up insert). "
            "Override: sex_detail_cu_strict:false."
        )

    # 双方脱尽：warning codes only (UNSTATED is info)
    both_undress_strict = spec.get("both_undress_strict")
    if both_undress_strict is None:
        both_undress_strict = _max_iron
    if both_undress_strict is True and "SEX_BOTH_UNDRESS_MISSING" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "both undress IRON failed (both_undress_strict): SEX_BOTH_UNDRESS_MISSING — "
            "插入时女≥undressed/bare；partner_wardrobe_state 若填写则 ≥undressed。 "
            "Override: both_undress_strict:false."
        )

    size_ladder_strict = spec.get("size_ladder_strict")
    if size_ladder_strict is None:
        ap = str(audience_profile or "").strip().lower()
        size_ladder_strict = _max_iron or ap in _hardcore_profiles
    # Only warning-severity SIZE_* hard-fail (info stays advisory even when strict)
    size_fail_codes = [
        str(i.get("code"))
        for i in (heat_rep.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code") or "").startswith("SIZE_")
        and str(i.get("severity") or "") == "warning"
    ]
    if size_ladder_strict is True and size_fail_codes:
        raise FilmSpecError(
            "size ladder failed (size_ladder_strict): "
            + ",".join(sorted(set(size_fail_codes)))
            + " — vary WS→MS→CU→insert; do not reopen wide mid-act. "
            "See size-ladder-hardcore-stack."
        )

    montage_strict = spec.get("montage_strict")
    if montage_strict is None:
        ap = str(audience_profile or "").strip().lower()
        montage_strict = _max_iron or ap in _hardcore_profiles
    montage_fail = [
        str(i.get("code"))
        for i in (heat_rep.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code") or "").startswith("MONTAGE_")
        and str(i.get("severity") or "") == "warning"
    ]
    if montage_strict is True and montage_fail:
        raise FilmSpecError(
            "montage craft failed (montage_strict): "
            + ",".join(montage_fail)
            + " — need insert/smash/montage variety. See montage-hardcore-male."
        )

    pose_strict = spec.get("pose_strict")
    if pose_strict is None:
        ap = str(audience_profile or "").strip().lower()
        pose_strict = _max_iron or ap in _hardcore_profiles
    if pose_strict is True and "SEX_POSE_STALE" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "sex pose variety failed (pose_strict): SEX_POSE_STALE — "
            "rotate sex_pose across act shots (straddle/cowgirl/from_behind…)."
        )

    vo_motion_strict = spec.get("sex_vo_motion_strict")
    if vo_motion_strict is None:
        ap = str(audience_profile or "").strip().lower()
        vo_motion_strict = _max_iron or ap in _hardcore_profiles
    if vo_motion_strict is True and "HEAT_VO_MOTION_MISMATCH" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "vo-motion align failed (sex_vo_motion_strict): HEAT_VO_MOTION_MISMATCH — "
            "mirror nar sex verbs in dsl.action/motion."
        )

    # Erotic impact scorecard — max IRON hard floor A (75) · 2026-07-29
    impact: dict[str, Any] | None = None
    with contextlib.suppress(Exception):
        impact = compute_erotic_impact_score(shots, heat_scale=heat_scale, heat_rep=heat_rep)
        spec["_erotic_impact"] = impact
    impact_strict = spec.get("erotic_impact_strict")
    if impact_strict is None:
        impact_strict = _max_iron
    impact_floor = float(spec.get("erotic_impact_floor") or 75.0)
    # Wave 4: always write heat-boost receipt when below S (agent loop)
    if impact is not None and heat_scale == "max" and film_root is not None:
        with contextlib.suppress(Exception):
            from pathlib import Path as _Path

            from edit_policy import suggest_impact_boost_actions
            from util import write_json as _write_json

            boost_plan = suggest_impact_boost_actions(
                shots,
                heat_scale=heat_scale,
                heat_rep=heat_rep,
                impact=impact,
                target_score=90.0,
            )
            rec_dir = _Path(film_root) / "receipts"
            rec_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                rec_dir / "heat-boost.json",
                {
                    "ok": True,
                    "kind": "heat-impact-boost",
                    "source": "write-spec",
                    "apply": False,
                    "heat_scale": heat_scale,
                    "plan": boost_plan,
                    "hint": "aifilm heat boost --root … --apply  # field patches toward S≥90",
                },
            )
            if boost_plan.get("needed"):
                notes = list(spec.get("_heat_notes") or [])
                notes.append(
                    f"heat-boost plan written (score={boost_plan.get('score')} "
                    f"gap={boost_plan.get('gap')} actions={len(boost_plan.get('actions') or [])}); "
                    "run heat boost --apply before bulk if below S"
                )
                spec["_heat_notes"] = notes
            # Optional auto field-patch (off by default)
            if (
                spec.get("auto_heat_boost") is True
                and boost_plan.get("needed")
                and float(impact.get("score") or 0) + 1e-9 < 90.0
            ):
                from edit_policy import apply_impact_boost_patches, apply_vo_spice_auto

                applied = apply_impact_boost_patches(shots, list(boost_plan.get("actions") or []))
                vo = apply_vo_spice_auto(shots, spice_level=str(spice_level or "extreme"))
                impact = compute_erotic_impact_score(
                    shots, heat_scale=heat_scale, heat_rep=heat_rep
                )
                spec["_erotic_impact"] = impact
                notes = list(spec.get("_heat_notes") or [])
                notes.append(
                    f"auto_heat_boost applied patches={applied.get('changed')} "
                    f"vo={vo.get('fixed')} → impact={impact.get('score')}"
                )
                spec["_heat_notes"] = notes
    if impact_strict is True and impact is not None:
        score = float(impact.get("score") or 0.0)
        if score + 1e-9 < impact_floor:
            raise FilmSpecError(
                f"erotic impact IRON failed (erotic_impact_strict): score={score} "
                f"< floor={impact_floor} (grade {impact.get('grade')}) — "
                "need sex≥50% + bare peak + 四拍弧 + 定器 CU + penetration verbs. "
                "Target grade A (≥75) / S (≥90). "
                "Run: aifilm heat boost --apply. "
                "Override: erotic_impact_strict:false or erotic_impact_floor."
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

    # Adult max has a separate sensory contract.  This is intentionally a
    # projection, not more prompt text: post/review can later bind it to media.
    try:
        from adult_max_director import apply_contract, validate_contract

        projection = apply_contract(spec, shots)
        sensory = validate_contract(spec, shots)
        spec["_adult_max_director"] = {**projection, **sensory}
        director = (
            spec.get("adult_max_director")
            if isinstance(spec.get("adult_max_director"), dict)
            else {}
        )
        if projection["active"] and director.get("strict", True) and not sensory["ok"]:
            raise FilmSpecError("adult max sensory contract failed: " + ",".join(sensory["codes"]))
    except ImportError:  # pragma: no cover - compatibility for partial installations
        pass

    return shots
