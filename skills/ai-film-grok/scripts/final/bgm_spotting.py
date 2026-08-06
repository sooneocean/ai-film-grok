"""BGM spotting stereo convert (closeout)."""
from __future__ import annotations
from typing import Any
import numpy as np
from final.errors import RenderError
from final.render_defaults import SR
from sound_plan import SoundPlanError, apply_mute_windows_to_samples, apply_sfx_accents_to_samples, expand_sound_events
try:
    from music_cue import apply_music_timeline_to_samples
except ImportError:
    apply_music_timeline_to_samples = None  # type: ignore

def apply_spotting_and_convert_to_stereo(float_bed: np.ndarray, *, sound_plan, shot_start_map, total_dur: float):
    try:
        spotting = expand_sound_events(sound_plan, shot_starts=shot_start_map, total_duration=float(total_dur))
    except SoundPlanError as exc:
        raise RenderError(str(exc)) from exc
    events = spotting.get("applied_events") or []
    if float_bed.ndim == 1:
        bgm_out = np.column_stack((float_bed, float_bed))
    elif float_bed.ndim == 2 and float_bed.shape[1] == 1:
        bgm_out = np.column_stack((float_bed[:, 0], float_bed[:, 0]))
    else:
        bgm_out = float_bed.copy()
    music_timeline = (sound_plan or {}).get("music_timeline") if isinstance(sound_plan, dict) else None
    if music_timeline and apply_music_timeline_to_samples is not None:
        bgm_out = apply_music_timeline_to_samples(bgm_out, sr=SR, timeline=music_timeline)
        spotting["music_cue_applied"] = "energy_duck_profile"
        spotting["music_cue_shot_count"] = len(music_timeline)
    else:
        spotting["music_cue_applied"] = "none"
    sfx_out = np.zeros_like(bgm_out)
    if events:
        bgm_out = apply_mute_windows_to_samples(bgm_out, sr=SR, events=events)
        sfx_out = apply_sfx_accents_to_samples(sfx_out, sr=SR, events=events, level=0.55)
        bgm_out = np.clip(bgm_out, -1.0, 1.0)
        sfx_out = np.clip(sfx_out, -1.0, 1.0)
        spotting["sfx_overlay_count"] = sum(1 for e in events if e.get("type") == "sfx_accent" and e.get("overlay_applied"))
    else:
        spotting["sfx_overlay_count"] = 0
    spotting["bed_source"] = spotting.get("bed_source") or "unknown"
    return bgm_out, sfx_out, spotting
