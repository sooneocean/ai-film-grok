"""VO/TTS/mix resolve for formal final (closeout)."""
from __future__ import annotations
import contextlib, os
from typing import Any
from final.render_defaults import DEFAULT_VO_GAIN, DEFAULT_VO_PITCH, DEFAULT_VO_RATE, DEFAULT_VOCAL_COLOR_GAIN
from final.native_audio import resolve_native_audio_volume
from final.voice import DEFAULT_VOICE, STORYTELLER_VOICE, normalize_cast_tts_backends, normalize_cast_voices
try:
    from voice_tracks import resolve_voice_tracks
except ImportError:
    resolve_voice_tracks = None  # type: ignore

def resolve_final_voice_mix_config(args: Any, spec: dict[str, Any]) -> dict[str, Any]:
    vo_mode = str(spec.get("vo_mode") or "storyteller").lower()
    voice = getattr(args, "voice", None) or spec.get("vo_voice") or (STORYTELLER_VOICE if vo_mode in ("storyteller", "hybrid") else DEFAULT_VOICE)
    cast_voices = normalize_cast_voices(spec.get("cast_voices") or {})
    vo_rate = str(getattr(args, "vo_rate", None) or spec.get("vo_rate") or DEFAULT_VO_RATE)
    vo_pitch = str(getattr(args, "vo_pitch", None) or spec.get("vo_pitch") or DEFAULT_VO_PITCH)
    vo_tts_vol = str(getattr(args, "vo_tts_volume", None) or spec.get("vo_tts_volume") or "+0%")
    tts_backend = getattr(args, "tts_backend", None) or spec.get("tts_backend") or os.environ.get("AIFILM_TTS_BACKEND") or "auto"
    tts_allow_network_fallback = bool(spec.get("tts_allow_network_fallback", False))
    cast_tts_backends = normalize_cast_tts_backends(spec.get("cast_tts_backends") or {})
    raw_gain = getattr(args, "vo_gain", None)
    if raw_gain is None:
        raw_gain = spec.get("vo_gain")
    vo_gain = float(raw_gain if raw_gain is not None else DEFAULT_VO_GAIN)
    voice_policy: dict[str, Any] = {}
    if resolve_voice_tracks is not None:
        try:
            voice_policy = resolve_voice_tracks(spec)
        except Exception:
            voice_policy = {}
    if voice_policy.get("nar_gain") is not None:
        with contextlib.suppress(TypeError, ValueError):
            vo_gain = float(voice_policy["nar_gain"])
    native_audio_volume = resolve_native_audio_volume(args, spec, voice_policy)
    raw_color_gain = getattr(args, "vocal_color_gain", None)
    if raw_color_gain is None:
        raw_color_gain = voice_policy.get("vocal_color_gain")
    if raw_color_gain is None:
        raw_color_gain = spec.get("vocal_color_gain")
    try:
        film_vocal_color_gain = float(raw_color_gain if raw_color_gain is not None else DEFAULT_VOCAL_COLOR_GAIN)
    except (TypeError, ValueError):
        film_vocal_color_gain = DEFAULT_VOCAL_COLOR_GAIN
    film_vocal_color_gain = max(0.0, min(1.5, film_vocal_color_gain))
    mood = getattr(args, "music_mood", None) or ("rnb" if vo_mode in ("storyteller", "hybrid") else "playful")
    lipsync_mode = (getattr(args, "lipsync", None) or "off").lower()
    return dict(vo_mode=vo_mode, voice=voice, cast_voices=cast_voices, vo_rate=vo_rate, vo_pitch=vo_pitch,
                vo_tts_vol=vo_tts_vol, tts_backend=tts_backend, tts_allow_network_fallback=tts_allow_network_fallback,
                cast_tts_backends=cast_tts_backends, vo_gain=vo_gain, voice_policy=voice_policy,
                native_audio_volume=native_audio_volume, film_vocal_color_gain=film_vocal_color_gain,
                mood=mood, lipsync_mode=lipsync_mode)
