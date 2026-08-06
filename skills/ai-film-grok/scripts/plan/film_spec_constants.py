"""Film-spec constants leaf (M1 peel · 2026-08-06).

Pure data / frozensets shared by validate and CLI. No I/O.
"""

from __future__ import annotations

from film_spec_profile import (
    FRW_I2V_FRW_ONLY_LIFEBOAT,
    frw_i2v_fallback_chain,
)

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
DEFAULT_FRW_ASPECT = "9:16"
DEFAULT_FRW_RESOLUTION = "720p"
DEFAULT_FRW_DURATION = "5"
DEFAULT_FRW_FPS = "24"
# LTX preferred pixel size for vertical shorts (probe-validated 2026-07-20)
DEFAULT_LTX_WIDTH = "704"
DEFAULT_LTX_HEIGHT = "1280"
# Explicit legacy FRW lifeboat; it is not part of the automatic action chain.
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
# Default I2V plate when duration_sec omitted.
# S0.1 · 2026-08-06: H3 single-clip nominal ~5.2s (not 6.0). Plan must not
# systematically invent slots longer than local H3 stretchability (~5.9s).
DEFAULT_DURATION_SEC = 5.2
# Soft report threshold (legacy); hard gate is est_vo_sec <= duration_sec + slack.
LOOP_RISK_VO_SEC = 5.5
# TTS estimate slack vs plate (actual edge-tts may drift slightly under estimate).
VO_PACING_SLACK_SEC = 0.5
# Beats that must never stream_loop in final (see edit_policy.plan_stretch forbid_loop).
NO_LOOP_DRAMATIC_FUNCTIONS = frozenset({"hook", "action"})


