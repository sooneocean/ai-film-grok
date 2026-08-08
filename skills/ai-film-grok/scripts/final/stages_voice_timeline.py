"""Narration + native track assembly (orchestrator relief W1.8).

Stage 5 of render_final: pad VO parts, acrossfade narration, build native track.
Structure-only; no mix policy retune.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from final.errors import RenderError
from final.media_ops import concat_audio_segments, pdur, run
from final.render_defaults import SR
from final.tts_tracks import build_native_track
from logger import log
from security_policy import SecurityPolicyError, safe_output_path


def build_narration_and_native_tracks(
    *,
    work: Path,
    audio_dir: Path,
    shot_audio: list[dict[str, Any]],
    title_dur: float,
    end_dur: float,
    transition_sec: float,
    xfade_plan: dict[str, Any],
    full_join_intents: list[Any],
    silence_wav: Callable[[Path, float], None],
) -> dict[str, Any]:
    """Build narration.wav + native track aligned to picture joins."""
    # 5) Build narration track with title/end silence + acrossfade matching video
    sil_t = work / "sil_t.wav"
    sil_e = work / "sil_e.wav"
    silence_wav(sil_t, title_dur)
    silence_wav(sil_e, end_dur)
    voice_inputs = [sil_t] + [item["wav"] for item in shot_audio] + [sil_e]
    # convert each to same format and pad to exact segment durations
    voice_parts: list[Path] = []
    segs_durs = [title_dur] + [item["target"] for item in shot_audio] + [end_dur]
    for i, (src, dur) in enumerate(zip(voice_inputs, segs_durs, strict=False)):
        part = work / f"vo_part_{i:02d}.wav"
        # pad/trim to exact duration
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-af",
                f"apad=pad_dur={dur:.3f},atrim=0:{dur:.3f},asetpts=PTS-STARTPTS",
                "-ar",
                str(SR),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(part),
            ]
        )
        voice_parts.append(part)
    try:
        voice_cat = safe_output_path(
            audio_dir, "narration.wav", suffixes={".wav"}, field="narration output"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    active_transition = transition_sec if xfade_plan.get("enabled") else 0.0
    audio_join_intents = (
        full_join_intents if xfade_plan.get("enabled") else ["hard"] * max(0, len(segs_durs) - 1)
    )
    # Placeholder to keep following code structure: voice_cat filled by acrossfade
    afade_plan = concat_audio_segments(
        voice_parts,
        voice_cat,
        transition_sec=active_transition,
        segment_durs=segs_durs,
        join_intents=audio_join_intents if xfade_plan.get("enabled") else None,
    )
    log(f"audio concat method={afade_plan.get('method')}")
    total_dur = pdur(voice_cat)
    native_track = build_native_track(
        shot_audio,
        title_duration=title_dur,
        end_duration=end_dur,
        work=work,
        audio_dir=audio_dir,
        transition_sec=active_transition,
        join_intents=audio_join_intents if xfade_plan.get("enabled") else None,
    )

    return {
        "voice_cat": voice_cat,
        "afade_plan": afade_plan,
        "total_dur": total_dur,
        "native_track": native_track,
        "active_transition": active_transition,
        "audio_join_intents": audio_join_intents,
        "segs_durs": segs_durs,
    }
