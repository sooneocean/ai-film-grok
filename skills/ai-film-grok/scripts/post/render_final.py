#!/usr/bin/env python3
"""Render a formal final film: edge-tts VO + BGM + FFmpeg plate.

Post lipsync removed (v2.40): dialogue uses native clip audio (prefer_native).
``--lipsync`` must stay ``off``. See references/lipsync.md.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np
from audio_cues import AudioCueError, compile_audio_timeline, primary_voice_cue, strict_tts_text
from audio_timeline import AudioTimelineError, build_mix_execution_plan, rebase_to_rendered_shots
from audio_timeline import caption_bindings as timeline_caption_bindings
from audio_timeline import compile_timeline as compile_audio_timeline_v1
from audio_timeline import timeline_hash as audio_timeline_hash
from checkpoint import CheckpointManager
from dialogue_broll import validate_broll_visual_review, write_broll_edit_report
from edit_policy import (
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    expand_story_join_intents,
    expand_story_join_styles,
    film_segment_timeline,
    normalize_transition_sec,
)
from event_voice_stem import EventVoiceStemError, render_event_voice_stem
from logger import log
from media_qa import MediaQAError, analyze_media, approved_clip_record
from narrative_timeline import (
    NarrativeTimelineError,
    _is_non_vo_coverage_shot,
    validate_sfx_scene_bindings,
)
from render_workspace import RenderWorkspaceError, prepare_render_workspace, resolve_render_paths
from runtime_policy import sha256
from scene_sound import reconcile as reconcile_scene_sound
from scene_sound_stems import SceneSoundError, render_scene_sound_stem
from security_policy import (
    SecurityPolicyError,
    atomic_write_text,
    safe_existing_file,
    safe_output_path,
)
from sound_plan import (
    SoundPlanError,
    build_mood_timeline,
    inject_auto_sfx_if_empty,
    resolve_loudnorm,
    resolve_music_template,
    resolve_sidechain,
    should_apply_loudnorm,
    sidechain_filter_fragment,
    validate_audio_tracks_contract,
)
from transition_ops import TransitionOperationError, bind_transition_operations_to_timeline
from util import utc_now, write_json
from util.errors import FilmError

# local sibling import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from lipsync_backend import LipSyncError, enforce_dialogue_lipsync
except ImportError:  # pragma: no cover
    enforce_dialogue_lipsync = None  # type: ignore

    class LipSyncError(FilmError):  # type: ignore
        pass

try:
    from music_cue import (
        apply_music_timeline_to_samples,
        build_music_mix_review,
        build_music_timeline,
        motif_seed,
        summarize_music_timeline,
    )
    from performance_cue import normalize_performance_cue, summarize_bgm_response
    from tts_backend import probe as tts_probe
    from tts_backend import synthesize as tts_synthesize
except ImportError:  # pragma: no cover
    tts_synthesize = None  # type: ignore
    tts_probe = None  # type: ignore
    normalize_performance_cue = None  # type: ignore
    summarize_bgm_response = None  # type: ignore
    apply_music_timeline_to_samples = None  # type: ignore
    build_music_mix_review = None  # type: ignore
    build_music_timeline = None  # type: ignore
    motif_seed = None  # type: ignore
    summarize_music_timeline = None  # type: ignore

try:
    from voice_tracks import (
        compute_color_offset_sec,
        resolve_shot_vocal_color,
        resolve_voice_tracks,
        sound_cues_to_sfx_kinds,
    )
except ImportError:  # pragma: no cover
    compute_color_offset_sec = None  # type: ignore
    resolve_shot_vocal_color = None  # type: ignore
    resolve_voice_tracks = None  # type: ignore
    sound_cues_to_sfx_kinds = None  # type: ignore


# R1/R1b/R1c peel: leaf helpers live in final/*; re-export for hard-compat.
from final.caption_text import (  # noqa: E402, F401
    _ensure_caption_density,
    _legacy_validate_linear_narration,
    _narration_fingerprint,
    _shot_speaker_key,
    _split_one_soft,
    build_subtitle_cues_for_shots,
    caption_text_for_shot,
    flatten_shots,
    is_character_speech_shot,
    narration_for_shot,
    split_units,
    spoken_text_for_shot,
    unit_timings,
    validate_linear_narration,
    write_srt,
)
from final.cards import (  # noqa: E402, F401
    FONT_CANDIDATES,
    _wrap_title_lines,
    mkcard_video,
    sub_png,
)
from final.enhance import (  # noqa: E402, F401
    build_post_enhancement_vf_chain,
    resolve_subtitle_mode,
)
from final.errors import RenderError, RenderTimeoutError  # noqa: E402, F401
from final.io import read_json  # noqa: E402, F401
from final.manifest import build_final_film_manifest_entry  # noqa: E402, F401
from final.media_ops import (  # noqa: E402, F401
    apply_dialogue_broll_visual,
    concat_audio_segments,
    concat_videos,
    pdur,
    resolve_join_transition_secs,
    run,
    stable_path_for_ffmpeg_filter,
    stretch_clip,
)
from final.native_audio import (  # noqa: E402, F401
    DEFAULT_NATIVE_AUDIO_VOLUME,
    FILM_NATIVE_STABLE_BASENAME,
    NATIVE_AUDIO_GAIN_MAX,
    NATIVE_AUDIO_GAIN_MIN,
    NATIVE_AUDIO_TARGET_DB,
    NATIVE_LIGHT_AF_FILTER,
    dialogue_lane_suppresses_native,
    dialogue_lane_tts_mix_gain,
    native_dialogue_replaced_by_post_tts,
    primary_native_shot_ids,
    resolve_dialogue_audio_lane,
    resolve_native_audio_gain,
    resolve_native_audio_volume,
)
from final.render_defaults import (  # noqa: E402, F401
    DEFAULT_BGM_GEN_AMP,
    DEFAULT_MUSIC_VOLUME,
    DEFAULT_SUB_MAX_CHARS,
    DEFAULT_VO_GAIN,
    DEFAULT_VO_PITCH,
    DEFAULT_VO_RATE,
    DEFAULT_VOCAL_COLOR_GAIN,
    SR,
)
from final.voice import (  # noqa: E402, F401
    _HEROINE_SPEAKERS,
    _NARRATOR_SPEAKERS,
    _PARTNER_SPEAKERS,
    DEFAULT_VOICE,
    HEROINE_ZH_VOICE,
    PARTNER_ZH_VOICE,
    STORYTELLER_VOICE,
    _locked_voice_role,
    normalize_cast_tts_backends,
    normalize_cast_voices,
    tts_backend_for_shot,
    validate_voice_language_locks,
    voice_for_shot,
)
from final.voice_mix_config import resolve_final_voice_mix_config  # noqa: E402, F401
from final.watchdog import _run_with_watchdog  # noqa: E402, F401


def resolve_font() -> str:
    """Resolve Chinese-capable font using this module's FONT_CANDIDATES (hard-compat patchable)."""
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return path
    raise RenderError("No Chinese-capable system font found")




# C5.3: read_json is re-exported from final.io (require_json_fnv) — no local copy.

from final.tts_tracks import (  # noqa: E402, F401
    DEFAULT_VOCAL_COLOR_GAIN as _TTS_DEFAULT_VOCAL_COLOR_GAIN,
)
from final.tts_tracks import (
    build_native_track,
    build_vocal_color_track,
)
from final.tts_tracks import (
    tts_synthesize as _tts_synthesize_default,
)
from final.tts_tracks import (
    tts_to_wav as _tts_to_wav_impl,
)
from render_final_music import (  # noqa: E402, F401
    _try_external_music_gen,
    make_tone,
    probe_mixed_loudness,
    procedural_music,
    procedural_music_rnb,
    render_music_template_timeline,
    silence_wav,
    write_wav_mono,
    write_wav_stereo,
)

# Hard-compat: tests monkeypatch render_final.tts_synthesize
tts_synthesize = _tts_synthesize_default




def tts_to_wav(*args, **kwargs):
    """Delegate to final.tts_tracks; honor patched ``tts_synthesize`` on this module."""
    kwargs.setdefault("synthesize", tts_synthesize)
    return _tts_to_wav_impl(*args, **kwargs)


def write_final_mix_partial_receipt(
    root: Path | str,
    *,
    prior_sc: str,
    error: str,
    mixed: Path | str,
    reason: str = "sidechain_mix_failed_amix_fallback",
    error_type: str | None = None,
    affected_tracks: list[str] | None = None,
) -> Path:
    """Delegate to mix_partial (P1-B honesty fields)."""
    from mix_partial import write_final_mix_partial_receipt as _write

    return _write(
        root,
        prior_sc=prior_sc,
        error=error,
        mixed=mixed,
        reason=reason,
        error_type=error_type,
        affected_tracks=affected_tracks,
    )


# W1 peel: pure helpers live in final.render_helpers; re-export for hard-compat.
from final.render_helpers import (  # noqa: E402, F401
    coerce_optional_float,
    resolve_plate_slot_sec,
    resolve_render_dimension,
)


def render_final(args: argparse.Namespace) -> dict[str, Any]:
    # W1.1 · bootstrap paths/spec/vo/workspace (leaf: final.render_context)
    from final.render_context import load_render_context

    ctx = load_render_context(
        args,
        tts_synthesize=tts_synthesize,
        tts_probe=tts_probe,
        resolve_font=resolve_font,
        enforce_dialogue_lipsync=enforce_dialogue_lipsync,
        lipsync_error_cls=LipSyncError,
    )
    root = ctx.root
    paths = ctx.paths
    out_dir = ctx.out_dir
    final_path = ctx.final_path
    manifest = ctx.manifest
    spec = ctx.spec
    scene_sound_report = ctx.scene_sound_report
    timeline = ctx.timeline
    width = ctx.width
    height = ctx.height
    fps = ctx.fps
    vo_mode = ctx.vo_mode
    voice = ctx.voice
    cast_voices = ctx.cast_voices
    vo_rate = ctx.vo_rate
    vo_pitch = ctx.vo_pitch
    vo_tts_vol = ctx.vo_tts_vol
    tts_backend = ctx.tts_backend
    tts_allow_network_fallback = ctx.tts_allow_network_fallback
    cast_tts_backends = ctx.cast_tts_backends
    vo_gain = ctx.vo_gain
    voice_policy = ctx.voice_policy
    native_audio_volume = ctx.native_audio_volume
    film_vocal_color_gain = ctx.film_vocal_color_gain
    mood = ctx.mood
    lipsync_mode = ctx.lipsync_mode
    tts_info = ctx.tts_info
    font_path = ctx.font_path
    shots = ctx.shots
    shot_voice_cues = ctx.shot_voice_cues
    clips_map = ctx.clips_map
    clips_dir = ctx.clips_dir
    audio_dir = ctx.audio_dir
    native_dir = ctx.native_dir
    work = ctx.work
    overlays_dir = ctx.overlays_dir
    checkpoint = ctx.checkpoint
    resume = ctx.resume
    dialogue_spoken_lang = ctx.dialogue_spoken_lang
    narration_spoken_lang = ctx.narration_spoken_lang
    _hb = ctx.heartbeat
    bgm_source_receipt: dict[str, Any] | None = ctx.bgm_source_receipt

    # 1) Per-shot TTS + H3 native XOR (leaf: final.stages_tts_stems)
    from final.stages_tts_stems import build_shot_audio_stems

    shot_audio = build_shot_audio_stems(
        root=root,
        shots=shots,
        clips_map=clips_map,
        clips_dir=clips_dir,
        audio_dir=audio_dir,
        native_dir=native_dir,
        work=work,
        args=args,
        vo_mode=vo_mode,
        voice=voice,
        cast_voices=cast_voices,
        vo_rate=vo_rate,
        vo_pitch=vo_pitch,
        vo_tts_vol=vo_tts_vol,
        tts_backend=tts_backend,
        tts_allow_network_fallback=tts_allow_network_fallback,
        cast_tts_backends=cast_tts_backends,
        film_vocal_color_gain=film_vocal_color_gain,
        dialogue_spoken_lang=dialogue_spoken_lang,
        narration_spoken_lang=narration_spoken_lang,
        voice_policy=voice_policy if isinstance(voice_policy, dict) else {},
        shot_voice_cues=shot_voice_cues,
        spec=spec,
        approved_clip_record=approved_clip_record,
        sha256=sha256,
        validate_broll_visual_review=validate_broll_visual_review,
        extract_native_audio=extract_native_audio,
        tts_to_wav=tts_to_wav,
        silence_wav=silence_wav,
    )

    # 2–4) Stretch + title/end + join concat (leaf: final.stages_picture_concat)
    from final.stages_picture_concat import assemble_picture_track

    _pic = assemble_picture_track(
        shot_audio=shot_audio,
        shots=shots,
        work=work,
        width=width,
        height=height,
        fps=fps,
        tts_backend=str(tts_backend),
        vo_mode=vo_mode,
        native_audio_volume=float(native_audio_volume),
        resume=resume,
        checkpoint=checkpoint,
        root=root,
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        manifest=manifest if isinstance(manifest, dict) else {},
        font_path=font_path,
        write_broll_edit_report=write_broll_edit_report,
        heartbeat=_hb,
    )
    stretched = _pic["stretched"]
    lipsync_report = _pic["lipsync_report"]
    broll_edit_report = _pic["broll_edit_report"]
    broll_edit_report_sha256 = _pic["broll_edit_report_sha256"]
    title_text = _pic["title_text"]
    end_text = _pic["end_text"]
    title_mp4 = _pic["title_mp4"]
    end_mp4 = _pic["end_mp4"]
    title_dur = _pic["title_dur"]
    end_dur = _pic["end_dur"]
    silent = _pic["silent"]
    transition_sec = _pic["transition_sec"]
    story_intents = _pic["story_intents"]
    default_intent = _pic["default_intent"]
    full_join_intents = _pic["full_join_intents"]
    full_join_styles = _pic["full_join_styles"]
    full_join_use_ts = _pic["full_join_use_ts"]
    transition_style = _pic["transition_style"]
    xfade_plan = _pic["xfade_plan"]

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

    # 6) Music
    try:
        music_path = safe_output_path(
            audio_dir, "bgm_procedural.wav", suffixes={".wav"}, field="BGM output"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    mix_spotting: dict[str, Any] = {
        "mood": mood,
        "bed": True,
        "applied_events": [],
        "total_duration": float(total_dur),
        "event_count": 0,
        "bed_applied": True,
        "voice_tracks": {
            "nar_gain": vo_gain,
            "vocal_color_gain": film_vocal_color_gain,
            "native_audio_volume": native_audio_volume,
            "policy": voice_policy,
        },
        "scene_sound_reconcile": scene_sound_report,
    }
    # Spotting map shared by procedural + user music (mute/duck/sfx on bed)
    spot_shot_targets = [float(item["target"]) for item in shot_audio]
    spot_tl = film_segment_timeline(
        title_duration=title_dur,
        shot_targets=spot_shot_targets,
        end_duration=end_dur,
        transition_sec=active_transition,
        story_join_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent if active_transition > 0 else "hard",
    )
    shot_start_map = {
        str(item["id"]): float(spot_tl["shot_starts"][i]) for i, item in enumerate(shot_audio)
    }
    # film_segment_timeline returns shot_starts only; durations stay in spot_shot_targets
    shot_end_map = {
        str(item["id"]): float(spot_tl["shot_starts"][i] + spot_shot_targets[i])
        for i, item in enumerate(shot_audio)
    }
    shot_duration_map = {str(item["id"]): float(item["target"]) for item in shot_audio}
    # Legacy cue sidecar remains byte-compatible.  v1 is opt-in and carries
    # all eight event types plus source/license/overlap validation.
    audio_timeline = compile_audio_timeline(shots, shot_starts=shot_start_map)
    # Do not claim unrendered foley/ambience/music was mixed. This is the
    # renderer-local cue receipt, distinct from the production audio timeline.
    audio_timeline_path = audio_dir / "audio-cues-timeline.json"
    formal_timeline: dict[str, Any] | None = None
    formal_silence_windows: list[dict[str, Any]] = []
    event_voice_stem: dict[str, Any] | None = None
    use_event_tts = bool(spec.get("audio_timeline_v1_event_tts", False))
    if bool(spec.get("audio_timeline_v1", False)):
        try:
            stored_timeline = (
                read_json(audio_dir / "audio-timeline.json") if use_event_tts else None
            )
            formal_timeline = (
                stored_timeline
                if isinstance(stored_timeline, dict)
                else compile_audio_timeline_v1(spec)
            )
            formal_timeline = rebase_to_rendered_shots(
                formal_timeline, shot_start_map, shot_durations=shot_duration_map
            )
            formal_timeline["duration_sec"] = round(float(total_dur), 3)
            execution_plan = build_mix_execution_plan(formal_timeline)
            formal_silence_windows = list(execution_plan.get("silence_windows") or [])
        except AudioTimelineError as exc:
            raise RenderError(str(exc)) from exc
        write_json(audio_timeline_path, formal_timeline)
        write_json(audio_dir / "audio-mix-execution-plan.json", execution_plan)
    else:
        write_json(audio_timeline_path, {"version": 1, "cues": audio_timeline})
    mix_spotting["audio_timeline"] = {
        "path": str(audio_timeline_path),
        "cue_count": len(formal_timeline["events"]) if formal_timeline else len(audio_timeline),
        "schema": "audio-timeline" if formal_timeline else "legacy-audio-cues",
        "sha256": audio_timeline_hash(formal_timeline)
        if formal_timeline
        else sha256(audio_timeline_path),
        "execution_plan": str(audio_dir / "audio-mix-execution-plan.json")
        if formal_timeline
        else None,
    }
    mix_spotting["formal_silence_windows"] = formal_silence_windows
    if use_event_tts:
        if formal_timeline is None:
            raise RenderError("audio_timeline_v1_event_tts requires audio_timeline_v1")
        event_voice_path = audio_dir / "event-voices.wav"
        event_manifest = read_json(audio_dir / "tts-manifest.json")
        if not isinstance(event_manifest, dict):
            raise RenderError("audio_timeline_v1_event_tts requires audio/tts-manifest.json")
        try:
            event_voice_stem = render_event_voice_stem(
                root,
                formal_timeline,
                event_manifest,
                duration_sec=float(total_dur),
                out=event_voice_path,
            )
        except EventVoiceStemError as exc:
            raise RenderError(str(exc)) from exc
        voice_cat = event_voice_path
        mix_spotting["event_voice_stem"] = event_voice_stem
    scene_sound_path = audio_dir / "scene_sound_stereo.wav"
    ambience_path = audio_dir / "ambience_stereo.wav"
    if formal_timeline is not None:
        try:
            scene_sound = render_scene_sound_stem(
                root,
                formal_timeline,
                duration_sec=float(total_dur),
                out=scene_sound_path,
                sample_rate=48000,
                ambience_out=ambience_path,
            )
        except SceneSoundError as exc:
            raise RenderError(str(exc)) from exc
    else:
        silence_wav(scene_sound_path, float(total_dur))
        silence_wav(ambience_path, float(total_dur))
        scene_sound = {
            "path": str(scene_sound_path),
            "event_count": 0,
            "events": [],
            "ambience": {"path": str(ambience_path), "event_count": 0, "events": []},
        }
    mix_spotting["scene_sound"] = scene_sound
    ambience_volume = (
        0.0
        if bool(getattr(args, "mute_ambience", False))
        else float(getattr(args, "ambience_volume", 1.0))
    )
    ambience_volume = max(0.0, min(2.0, ambience_volume))
    mix_spotting["ambience"] = {
        **(scene_sound.get("ambience") or {}),
        "volume": ambience_volume,
        "muted": ambience_volume == 0.0,
        "ducking": "preserved_under_narration",
    }
    sound_plan = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else None
    if sound_plan is None:
        sound_plan = {}
    try:
        validate_sfx_scene_bindings(
            sound_plan,
            [shot for shot in flatten_shots(spec) if isinstance(shot, dict)],
        )
    except NarrativeTimelineError as exc:
        raise RenderError(str(exc)) from exc
    # Auto light SFX accents from dramatic_function when author left events empty
    flat = {str(s["id"]): s for s in flatten_shots(spec) if isinstance(s, dict) and s.get("id")}
    shot_dicts = [flat.get(str(item["id"]), {"id": item["id"]}) for item in shot_audio]
    try:
        from music_director import apply_bgm_to_shots, load_plan

        _md_plan = load_plan(root)
        if _md_plan is not None:
            _n_bgm = apply_bgm_to_shots(shot_dicts, _md_plan)
            mix_spotting["music_director_bgm"] = {
                "ok": True,
                "patched_shots": _n_bgm,
                "default_mood": (_md_plan.get("bgm") or {}).get("default_mood"),
            }
    except Exception as exc:  # noqa: BLE001
        mix_spotting["music_director_bgm"] = {"ok": False, "error": str(exc)[:160]}
    heat_scale = str(spec.get("heat_scale") or "").strip().lower() or None
    sound_plan = inject_auto_sfx_if_empty(sound_plan, shot_dicts, heat_scale=heat_scale)
    # sound_cues on shots → extra sfx_accent events (声景轨，不进旁白)
    if sound_cues_to_sfx_kinds is not None and isinstance(sound_plan, dict):
        cue_events: list[dict[str, Any]] = list(sound_plan.get("events") or [])
        added = 0
        for sh in shot_dicts:
            if not isinstance(sh, dict):
                continue
            kinds = sh.get("_sfx_kinds_from_cues") or sound_cues_to_sfx_kinds(
                sh.get("sound_cues") or []
            )
            for kind in list(kinds)[:2]:
                cue_events.append(
                    {
                        "type": "sfx_accent",
                        "shot_id": sh.get("id"),
                        "kind": kind,
                        "source": "sound_cues",
                    }
                )
                added += 1
        if added:
            sound_plan = {**sound_plan, "events": cue_events}
            notes = list(sound_plan.get("_notes") or [])
            notes.append(f"sound_cues: injected {added} sfx_accent(s)")
            sound_plan["_notes"] = notes

    # vocal_color timeline stem (after shot_starts known); default off → None
    color_track = build_vocal_color_track(
        shot_audio,
        shot_start_map=shot_start_map,
        total_duration=float(total_dur),
        work=work,
        audio_dir=audio_dir,
    )
    if color_track is not None:
        mix_spotting["vocal_color_track"] = str(color_track)
        mix_spotting["vocal_color_shots"] = [
            {
                "id": it.get("id"),
                "text": it.get("color_text"),
                "gain": it.get("color_gain"),
                "source": it.get("color_source"),
            }
            for it in shot_audio
            if it.get("color_wav")
        ]
        log(f"vocal_color track: {len(mix_spotting['vocal_color_shots'])} stem(s)")
    else:
        mix_spotting["vocal_color_track"] = None
        mix_spotting["vocal_color_shots"] = []
        log("vocal_color track: off (nar+BGM dominate; opt-in via voice_tracks.enabled)")

    def _apply_spotting_and_convert_to_stereo(
        float_bed: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        from final.bgm_spotting import apply_spotting_and_convert_to_stereo as _spot
        return _spot(
            float_bed,
            sound_plan=sound_plan,
            shot_start_map=shot_start_map,
            total_dur=float(total_dur),
        )


    # W1.2 · music seed / anti-fatigue / bed materialize (leaf: final.stages_music_bed)
    from final.stages_music_bed import (
        apply_plan_mood,
        enrich_sound_plan_music_timelines,
        materialize_music_bed,
        resolve_music_seed,
        run_bgm_anti_fatigue,
    )

    mood = apply_plan_mood(mood, sound_plan if isinstance(sound_plan, dict) else None)
    music_seed, ap, mood = resolve_music_seed(
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        root=root,
        mood=mood,
        total_dur=float(total_dur),
    )
    hard_fat = run_bgm_anti_fatigue(
        root=root,
        args=args,
        sound_plan=sound_plan if isinstance(sound_plan, dict) else None,
        mix_spotting=mix_spotting,
        mood=mood,
        music_seed=music_seed,
        total_dur=float(total_dur),
        ap=ap,
    )
    if isinstance(sound_plan, dict):
        sound_plan = enrich_sound_plan_music_timelines(
            sound_plan=sound_plan,
            mix_spotting=mix_spotting,
            mood=mood,
            total_dur=float(total_dur),
            hard_fat=hard_fat,
            shot_dicts=shot_dicts,
            shot_start_map=shot_start_map,
            shot_end_map=shot_end_map,
            build_mood_timeline=build_mood_timeline,
            build_music_timeline=build_music_timeline,
            summarize_music_timeline=summarize_music_timeline,
            render_error_cls=RenderError,
        )

    bed = materialize_music_bed(
        root=root,
        work=work,
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        sound_plan=sound_plan if isinstance(sound_plan, dict) else None,
        mix_spotting=mix_spotting,
        mood=mood,
        music_seed=music_seed,
        total_dur=float(total_dur),
        title_dur=float(title_dur),
        shot_audio=shot_audio,
        ap=ap,
        apply_spotting=_apply_spotting_and_convert_to_stereo,
        resolve_music_template=resolve_music_template,
        render_music_template_timeline=render_music_template_timeline,
        try_external_music_gen=_try_external_music_gen,
        procedural_music=procedural_music,
        write_wav_stereo=write_wav_stereo,
        run=run,
        sample_rate=SR,
        default_bgm_gen_amp=DEFAULT_BGM_GEN_AMP,
        render_error_cls=RenderError,
        sound_plan_error_cls=SoundPlanError,
    )
    music_path = bed["music_path"]
    sfx_stereo_path = bed["sfx_stereo_path"]
    license_note = bed["license_note"]
    mix_spotting = bed["mix_spotting"]
    music_resolved = bed["music_resolved"]
    bgm_source_receipt = bed["bgm_source_receipt"]
    mood = bed["mood"]

    # 7) Dual-track mix: VO primary + BGM always audible (两条音轨)
    # Sidechain: rnb default longer release so groove returns in VO pauses (Phase E)
    try:
        mixed = safe_output_path(
            audio_dir, "mixed.wav", suffixes={".wav"}, field="mixed audio output"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    music_vol = float(args.music_volume)
    performance_bgm = (
        summarize_bgm_response(spec.get("shots") or [])
        if summarize_bgm_response is not None
        else {"shots": 0, "mean_intensity": 0.0, "music_gain": 1.0, "duck_db": -2.0}
    )
    music_vol = max(0.02, min(1.0, music_vol * float(performance_bgm.get("music_gain", 1.0))))
    mix_spotting["performance_bgm"] = performance_bgm
    # Recipe bed_gain also nudges mix music_volume once (author CLI still wins base)
    try:
        bg_hint = float(
            (sound_plan or {}).get("bed_gain_hint")
            or (spec.get("_audio_routing") or {}).get("mean_bed_gain")
            or 1.0
        )
        if abs(bg_hint - 1.0) > 0.02:
            music_vol = max(0.02, min(1.0, music_vol * bg_hint))
            mix_spotting["music_vol_after_recipe"] = music_vol
    except (TypeError, ValueError):
        pass
    if isinstance(spec.get("_audio_routing"), dict):
        mix_spotting["audio_routing_counts"] = (spec.get("_audio_routing") or {}).get("counts")
        mix_spotting["audio_policy"] = (spec.get("audio_policy") or {}).get("mode")
    sc_overrides = {
        "threshold": getattr(args, "sidechain_threshold", None),
        "ratio": getattr(args, "sidechain_ratio", None),
        "attack_ms": getattr(args, "sidechain_attack", None),
        "release_ms": getattr(args, "sidechain_release", None),
    }
    try:
        sidechain = resolve_sidechain(
            sound_plan if isinstance(sound_plan, dict) else None,
            mood=mood,
            overrides=sc_overrides,
        )
    except SoundPlanError as exc:
        raise RenderError(str(exc)) from exc
    mix_spotting["sidechain"] = sidechain
    if performance_bgm.get("shots"):
        sidechain["performance_duck_db"] = performance_bgm.get("duck_db")
    sc_frag = sidechain_filter_fragment(sidechain)
    filters_help = run(["ffmpeg", "-filters"], check=False).stdout
    # I1.4 · default broadband duck (no acrossover) — leaf: final.stages_dual_mix
    from final.stages_dual_mix import apply_mix_path_env_policy

    filters_help = apply_mix_path_env_policy(filters_help, mix_spotting=mix_spotting)

    try:
        from acoustic_policy import resolve_acoustic_space

        v_motifs = (spec.get("director_intent") or {}).get("visual_motifs") or []
        loc_tags = [str(x) for x in v_motifs]
        ac = resolve_acoustic_space(loc_tags)
        # P0 · 2026-07-23: aecho on full ~60s stems hung ffmpeg 50+ min (wall clock).
        # Keep EQ only; reverb can be opt-in via film-spec acoustic_reverb=true later.
        sfx_dsp = f"highpass=f={ac['highpass']},lowpass=f={ac['lowpass']}"
        if bool((spec.get("audio_policy") or {}).get("acoustic_reverb")) or bool(
            os.environ.get("AIFILM_SFX_REVERB", "").strip() in {"1", "true", "yes"}
        ):
            sfx_dsp += f",aecho=1.0:1.0:{ac['reverb_time'] * 1000}:{ac['wet_level']}"
    except Exception:
        sfx_dsp = "anull"
    mix_spotting["sfx_dsp_applied"] = sfx_dsp

    use_color = color_track is not None and Path(str(color_track)).is_file()
    color_in_gain = 1.0  # per-stem gain already applied in build_vocal_color_track

    mix_sample_rate = 48000 if bool(spec.get("audio_timeline_v1", False)) else SR
    fc_parts = [
        f"[0:a]volume={vo_gain:.3f},aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo[narr]",
        f"[1:a]volume={music_vol:.3f},aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo[mus]",
        f"[2:a]volume={native_audio_volume:.3f},aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo[native]",
        f"[3:a]volume=1.0,aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo,{sfx_dsp}[sfx]",
        f"[4:a]volume=1.0,aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo[scene]",
        f"[5:a]volume={ambience_volume:.3f},aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo[ambience]",
    ]
    if use_color:
        fc_parts.append(
            f"[6:a]volume={color_in_gain:.3f},aformat=sample_fmts=fltp:sample_rates={mix_sample_rate}:channel_layouts=stereo[color]"
        )

    controlled_labels = {
        "music": "mus",
        "native": "native",
        "sfx": "sfx",
        "scene_sound": "scene",
        "ambience": "ambience",
    }
    for window_index, window in enumerate(formal_silence_windows):
        scope = str(window.get("scope") or "bed")
        targets = (
            ("music", "native", "sfx", "scene_sound", "ambience") if scope == "bed" else (scope,)
        )
        for target in targets:
            incoming = controlled_labels[target]
            outgoing = f"{target}_silence_{window_index}"
            fc_parts.append(
                f"[{incoming}]volume=0:enable='between(t,{float(window['start_sec']):.3f},{float(window['end_sec']):.3f})'[{outgoing}]"
            )
            controlled_labels[target] = outgoing
    music_label = controlled_labels["music"]
    native_label = controlled_labels["native"]
    sfx_label = controlled_labels["sfx"]
    scene_label = controlled_labels["scene_sound"]
    ambience_label = controlled_labels["ambience"]

    if "sidechaincompress" in filters_help and "acrossover" in filters_help:
        # Native I2V audio is the main picture sound.  Route it through the
        # same narration sidechain as BGM, so that it returns to full level in
        # gaps but does not bury narration or character dialogue.
        fc_parts.append(
            f"[{music_label}][{native_label}][{scene_label}]amix=inputs=3:duration=longest:normalize=0[picture_bed]"
        )
        fc_parts.append("[picture_bed]acrossover=split=300 4000[mus_l][mus_m][mus_h]")
        fc_parts.append("[narr]asplit[narr_main][narr_sc]")
        fc_parts.append(f"[mus_m][narr_sc]{sc_frag}[mus_m_ducked]")
        fc_parts.append(
            "[mus_l][mus_m_ducked][mus_h]amix=inputs=3:duration=longest:normalize=0[mus_ducked]"
        )
        fc_parts.append(
            f"[mus_ducked][{sfx_label}][{ambience_label}]amix=inputs=3:duration=longest:normalize=0[bed]"
        )
        final_amix_count = 2 + (1 if use_color else 0)
        color_in = "[color]" if use_color else ""
        fc_parts.append(
            f"[narr_main][bed]{color_in}amix=inputs={final_amix_count}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        mix_spotting["sidechain_applied"] = "dynamic_eq"
    elif "sidechaincompress" in filters_help:
        fc_parts.append(
            f"[{music_label}][{native_label}][{scene_label}]amix=inputs=3:duration=longest:normalize=0[picture_bed]"
        )
        fc_parts.append(f"[picture_bed][narr]{sc_frag}[ducked]")
        fc_parts.append(
            f"[ducked][{sfx_label}][{ambience_label}]amix=inputs=3:duration=longest:normalize=0[bed]"
        )
        final_amix_count = 2 + (1 if use_color else 0)
        color_in = "[color]" if use_color else ""
        fc_parts.append(
            f"[narr][ducked]{color_in}amix=inputs={final_amix_count}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        mix_spotting["sidechain_applied"] = "broadband"
    else:
        final_amix_count = 6 + (1 if use_color else 0)
        color_in = "[color]" if use_color else ""
        fc_parts.append(
            f"[narr][{music_label}][{native_label}][{sfx_label}][{scene_label}][{ambience_label}]{color_in}amix=inputs={final_amix_count}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        mix_spotting["sidechain_applied"] = False

    if build_music_mix_review is not None:
        mix_spotting["music_mix_review"] = build_music_mix_review(
            (sound_plan or {}).get("music_timeline") or [],
            sidechain_applied=mix_spotting["sidechain_applied"],
        )

    fc = ";".join(fc_parts)
    mix_spotting["mix_inputs"] = [
        "narration",
        "bgm",
        "native",
        "sfx",
        "scene_sound",
        "ambience",
    ] + (["vocal_color"] if use_color else [])
    preserved_native_shots = primary_native_shot_ids(shot_audio)
    suppressed_native_shots = [
        item["id"] for item in shot_audio if item.get("native_audio_suppressed_for_tts")
    ]
    native_dialogue_shots = [
        item["id"] for item in shot_audio if item.get("dialogue_audio_lane") == "native"
    ]
    post_tts_dialogue_shots = [
        item["id"] for item in shot_audio if item.get("dialogue_audio_lane") == "post_tts"
    ]
    # Fail-closed bookkeeping: same shot must never keep native + audible TTS.
    from final.stages_dual_mix import dialogue_xor_violations

    xor_violations = dialogue_xor_violations(shot_audio)
    if xor_violations:
        raise RenderError(
            "dialogue audio XOR violated (native + TTS both audible) for: "
            + ", ".join(xor_violations)
        )
    mix_spotting["native_audio"] = {
        "role": (
            "primary_video_sound"
            if preserved_native_shots
            else "suppressed_for_tts"
            if suppressed_native_shots
            else "unavailable"
        ),
        "volume": native_audio_volume,
        "preserved_shots": preserved_native_shots,
        "suppressed_for_tts_shots": suppressed_native_shots,
        "dialogue_xor": True,
        "native_dialogue_shots": native_dialogue_shots,
        "post_tts_dialogue_shots": post_tts_dialogue_shots,
        "xor_violations": [],
        "shot_lanes": {
            item["id"]: {
                "lane": item.get("dialogue_audio_lane"),
                "tts_mix_gain": item.get("tts_mix_gain"),
                "caption_clock_only": item.get("caption_clock_only"),
            }
            for item in shot_audio
        },
        "gain_plan": {
            item["id"]: item["native_audio_gain"] for item in shot_audio if item.get("native_audio")
        },
        "ducked_under_narration": "sidechaincompress" in filters_help,
    }

    try:
        mix_report_path = safe_output_path(
            audio_dir, "mix_report.json", suffixes={".json"}, field="mix report"
        )
        atomic_write_text(
            mix_report_path,
            json.dumps(mix_spotting, ensure_ascii=False, indent=2) + "\n",
        )
        mix_spotting["report_path"] = str(mix_report_path)
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc

    mix_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_cat),
        "-i",
        str(music_path),
        "-i",
        str(native_track),
        "-i",
        str(sfx_stereo_path),
        "-i",
        str(scene_sound_path),
        "-i",
        str(ambience_path),
    ]
    if use_color:
        mix_cmd.extend(["-i", str(color_track)])
    mix_cmd.extend(
        [
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-ar",
            str(mix_sample_rate),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(mixed),
        ]
    )
    # Wave D · sidechain can hang or fail mid-plate → simple amix PARTIAL (not silent)
    _hb("audio_mix", "sidechain_or_amix")
    from final.stages_dual_mix import run_sidechain_mix_with_amix_fallback

    run_sidechain_mix_with_amix_fallback(
        mix_cmd=mix_cmd,
        voice_cat=voice_cat,
        music_path=music_path,
        native_track=native_track,
        sfx_stereo_path=sfx_stereo_path,
        scene_sound_path=scene_sound_path,
        ambience_path=ambience_path,
        color_track=color_track if use_color else None,
        use_color=use_color,
        mixed=mixed,
        mix_sample_rate=mix_sample_rate,
        mix_spotting=mix_spotting,
        root=root,
        run=run,
        log=log,
        write_partial_receipt=write_final_mix_partial_receipt,
        render_error_cls=RenderError,
    )

    # Phase F/G: loudness probe + optional/auto loudnorm toward shortform target
    try:
        loud_policy = resolve_loudnorm(
            sound_plan if isinstance(sound_plan, dict) else None,
            mode=getattr(args, "loudnorm", None),
            target_lufs=getattr(args, "target_lufs", None),
        )
    except SoundPlanError as exc:
        raise RenderError(str(exc)) from exc
    mix_spotting["loudnorm_policy"] = loud_policy
    try:
        loud = probe_mixed_loudness(mixed)
        if loud:
            mix_spotting["loudness_before"] = loud
            mix_spotting["loudness"] = loud
            if build_music_mix_review is not None:
                mix_spotting["music_mix_review"] = build_music_mix_review(
                    (sound_plan or {}).get("music_timeline") or [],
                    sidechain_applied=mix_spotting.get("sidechain_applied", False),
                    loudness=loud,
                )
        measured = (loud or {}).get("integrated_lufs") if loud else None
        apply_ln, ln_reason = should_apply_loudnorm(loud_policy, measured)
        mix_spotting["loudnorm_decision"] = {"apply": apply_ln, "reason": ln_reason}
        if apply_ln:
            tgt = float(loud_policy["target_lufs"])
            normed = work / "mixed_loudnorm.wav"
            log(f"loudnorm apply → I={tgt:.1f} LUFS ({ln_reason})")
            ln_proc = run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(mixed),
                    "-af",
                    f"loudnorm=I={tgt:.1f}:TP=-1.5:LRA=11",
                    "-ar",
                    str(mix_sample_rate),
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(normed),
                ],
                check=False,
            )
            if ln_proc.returncode == 0 and normed.is_file() and normed.stat().st_size > 1000:
                import shutil as _shutil

                _shutil.copy2(normed, mixed)
                mix_spotting["loudnorm_applied"] = True
                loud_after = probe_mixed_loudness(mixed)
                if loud_after:
                    mix_spotting["loudness_after"] = loud_after
                    mix_spotting["loudness"] = loud_after
            else:
                mix_spotting["loudnorm_applied"] = False
                mix_spotting["loudnorm_error"] = (
                    ln_proc.stderr or ln_proc.stdout or "loudnorm failed"
                )[-400:]
        else:
            mix_spotting["loudnorm_applied"] = False
        if build_music_mix_review is not None:
            mix_spotting["music_mix_review"] = build_music_mix_review(
                (sound_plan or {}).get("music_timeline") or [],
                sidechain_applied=mix_spotting.get("sidechain_applied", False),
                loudness=mix_spotting.get("loudness"),
            )
        mix_spotting["artifacts"] = {
            "narration": {"path": str(voice_cat), "sha256": sha256(voice_cat)},
            "bgm": {"path": str(music_path), "sha256": sha256(music_path)},
            "native": {"path": str(native_track), "sha256": sha256(native_track)},
            "sfx": {"path": str(sfx_stereo_path), "sha256": sha256(sfx_stereo_path)},
            "scene_sound": {"path": str(scene_sound_path), "sha256": sha256(scene_sound_path)},
            "ambience": {"path": str(ambience_path), "sha256": sha256(ambience_path)},
            "mixed": {"path": str(mixed), "sha256": sha256(mixed)},
        }
        if bool(getattr(args, "export_stems", False)):
            stems_dir = audio_dir / "stems"
            if stems_dir.is_symlink():
                raise RenderError("audio stems directory cannot be a symbolic link")
            stems_dir.mkdir(parents=True, exist_ok=True)
            exported_stems: dict[str, dict[str, str]] = {}
            for name, source in (
                ("narration.wav", voice_cat),
                ("bgm.wav", music_path),
                ("native.wav", native_track),
                ("sfx.wav", sfx_stereo_path),
                ("scene_sound.wav", scene_sound_path),
                ("ambience.wav", ambience_path),
            ):
                target = safe_output_path(stems_dir, name, suffixes={".wav"}, field="audio stem")
                shutil.copy2(source, target)
                exported_stems[name.removesuffix(".wav")] = {
                    "path": str(target),
                    "sha256": sha256(target),
                }
            if use_color:
                target = safe_output_path(
                    stems_dir, "vocal_color.wav", suffixes={".wav"}, field="audio stem"
                )
                shutil.copy2(color_track, target)
                exported_stems["vocal_color"] = {"path": str(target), "sha256": sha256(target)}
            mix_spotting["exported_stems"] = exported_stems
        if mix_spotting.get("report_path"):
            atomic_write_text(
                Path(str(mix_spotting["report_path"])),
                json.dumps(mix_spotting, ensure_ascii=False, indent=2) + "\n",
            )
        validate_audio_tracks_contract(spec, audio_dir=audio_dir, require_artifacts=True)
    except SoundPlanError:
        raise
    except Exception as exc:  # pragma: no cover — probe must never fail final
        mix_spotting["loudness_error"] = str(exc)[:200]
        if mix_spotting.get("report_path"):
            with contextlib.suppress(Exception):
                atomic_write_text(
                    Path(str(mix_spotting["report_path"])),
                    json.dumps(mix_spotting, ensure_ascii=False, indent=2) + "\n",
                )

    # 8) Subtitle cues + SRT + optional PIL burn (leaf: final.stages_subs)
    from final.stages_subs import materialize_subs_stage

    _subs = materialize_subs_stage(
        args=args,
        out_dir=out_dir,
        audio_dir=audio_dir,
        work=work,
        overlays_dir=overlays_dir,
        silent=silent,
        shot_audio=shot_audio,
        shot_dicts=shot_dicts,
        title_duration=float(title_dur),
        end_duration=float(end_dur),
        active_transition=float(active_transition),
        story_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent,
        use_event_tts=use_event_tts,
        formal_timeline=formal_timeline,
        timeline_caption_bindings=timeline_caption_bindings,
        width=width,
        height=height,
        font_path=font_path,
        run=run,
        render_error_cls=RenderError,
    )
    cues = _subs["cues"]
    film_tl = _subs["film_tl"]
    event_caption_bindings = _subs["event_caption_bindings"]
    srt_path = _subs["srt_path"]
    srt_stable = _subs["srt_stable"]
    video_subbed = _subs["video_subbed"]
    subs_mode = _subs["subs_mode"]

    # 9) Mux final + verify streams (leaf: final.stages_mux_manifest)
    from final.stages_mux_manifest import mux_final_mp4, verify_final_streams

    mux_final_mp4(video_subbed=video_subbed, mixed=mixed, final_path=final_path, run=run)
    streams = verify_final_streams(
        final_path=final_path,
        audio_timeline_v1=bool(spec.get("audio_timeline_v1", False)),
        run=run,
        render_error_cls=RenderError,
    )

    timeline_path = root / "timeline.json"
    mix_report_path = root / "audio" / "mix_report.json"
    try:
        bound_transition_ops = bind_transition_operations_to_timeline(
            list(spec.get("transition_ops") or []), film_timeline=film_tl
        )
    except TransitionOperationError as exc:
        raise RenderError(f"transition operation timing: {exc}") from exc
    report = {
        "schema_version": 2,
        "created_at": utc_now(),
        "title": title_text,
        "output": str(final_path),
        "output_sha256": sha256(final_path),
        "duration_sec": pdur(final_path),
        "width": width,
        "height": height,
        "fps": fps,
        "vo_mode": vo_mode,
        "voice": voice,
        "transition": {
            "sec": transition_sec,
            "active_sec": active_transition,
            "story_intents": story_intents,
            "full_join_intents": full_join_intents,
            "default_intent": default_intent,
            "video": xfade_plan,
            "audio": afade_plan,
            "operations": bound_transition_ops,
            "film_timeline": {
                "shot_starts": film_tl.get("shot_starts"),
                "output_duration": film_tl.get("output_duration"),
                "use_ts": film_tl.get("use_ts"),
                "enabled": film_tl.get("enabled"),
                "join_intents": film_tl.get("full_join_intents") or film_tl.get("join_intents"),
            },
        },
        "sound_spotting": mix_spotting,
        "dialogue_broll": broll_edit_report,
        "dialogue_broll_report_sha256": broll_edit_report_sha256,
        "tts": {
            "backend_requested": tts_backend,
            "cast_tts_backends": cast_tts_backends,
            "probe": tts_info,
            "shots": [item.get("tts") for item in shot_audio],
        },
        "narration": {"path": str(voice_cat), "sha256": sha256(voice_cat)},
        "music": {
            "path": str(music_path),
            "sha256": sha256(music_path) if Path(music_path).is_file() else None,
            "license_or_source": license_note,
            "volume": music_vol,
            "ducked_under_narration": "sidechaincompress" in filters_help,
            "mood": mood,
            "bed_source": mix_spotting.get("bed_source"),
            "bgm_source": bgm_source_receipt,
            "honest_limits": (bgm_source_receipt or {}).get("honest_limits") or [],
        },
        "native_audio": {
            "path": str(native_track),
            "sha256": sha256(native_track),
            "volume": native_audio_volume,
            "role": mix_spotting["native_audio"]["role"],
            "ducked_under_narration": "sidechaincompress" in filters_help,
            "preserved_shots": preserved_native_shots,
            "suppressed_for_tts_shots": suppressed_native_shots,
        },
        "audio_provenance": {
            "mix_report": str(mix_report_path) if mix_report_path.is_file() else None,
            "mix_report_sha256": sha256(mix_report_path) if mix_report_path.is_file() else None,
            "audio_timeline": str(audio_timeline_path) if audio_timeline_path.is_file() else None,
            "audio_timeline_sha256": sha256(audio_timeline_path)
            if audio_timeline_path.is_file()
            else None,
            "audio_mix_execution_plan": str(audio_dir / "audio-mix-execution-plan.json")
            if formal_timeline
            else None,
        },
        "timeline": {
            "path": str(timeline_path) if timeline_path.is_file() else None,
            "sha256": sha256(timeline_path) if timeline_path.is_file() else None,
        },
        "subtitles": {
            "srt": str(srt_path),
            "srt_stable": str(srt_stable) if srt_stable != srt_path else None,
            "srt_sha256": sha256(srt_path),
            "cue_count": len(cues),
            "burned_in": subs_mode == "burn",
            "mode": subs_mode,
            "audio_event_bindings": timeline_caption_bindings(formal_timeline)
            if formal_timeline
            else None,
        },
        "shots": [
            {
                "id": item["id"],
                "text": item["text"],
                "vo_dur": item["vo_dur"],
                "raw_vo_dur": item.get("raw_vo_dur"),
                "target": item["target"],
                "stretch_plan": item.get("stretch_plan"),
                "vo_atempo_plan": item.get("vo_atempo_plan"),
                "visual_fit": item.get("visual_fit"),
                "vo_fit": item.get("vo_fit"),
                "tts": item.get("tts"),
            }
            for item in shot_audio
        ],
        "provider_visual": "grok-imagine",
        "post_engine": "ai-film-grok/render_final.py",
        "lipsync": {
            "mode": "off",
            "frozen": True,
            "shots": lipsync_report,
        },
    }
    try:
        report_path = safe_output_path(
            out_dir, "final-delivery.json", suffixes={".json"}, field="delivery report"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    write_json(report_path, report)

    try:
        technical_qa = analyze_media(final_path, require_audio=True, require_motion=True)
    except MediaQAError as exc:
        raise RenderError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise RenderError(f"Final MP4 failed technical QA: {technical_qa.get('errors')}")
    report["technical_qa"] = technical_qa
    if str(spec.get("production_mode") or "shortform") == "longform":
        from longform import LongformError, materialize_unit_masters

        try:
            report["longform_unit_masters"] = materialize_unit_masters(
                root,
                final_path=final_path,
                film_timeline=film_tl,
                shots=shot_audio,
            )
        except LongformError as exc:
            raise RenderError(f"longform unit masters: {exc}") from exc
    write_json(report_path, report)

    try:
        from timeline_clock import persist_film_timeline

        report["film_timeline_receipt"] = str(persist_film_timeline(root, film_tl))
        write_json(report_path, report)
    except Exception as tl_exc:  # noqa: BLE001
        report["film_timeline_receipt_error"] = str(tl_exc)[:160]

    # Update manifest gates (default technical final truth, overwritten after official final check).
    manifest.setdefault("outputs", {})["final_film"] = build_final_film_manifest_entry(
        final_path=final_path,
        output_sha256=report["output_sha256"],
        duration_sec=report["duration_sec"],
        report_path=report_path,
        technical_qa=technical_qa,
        official_final={"delivery_visibility": "technical_final_visible", "status": "TECHNICAL_FINAL"},
    )
    # Technical success is not human/agent end-to-end approval.
    manifest.setdefault("gates", {})["final_complete"] = False
    manifest["updated_at"] = utc_now()
    write_json(root / "manifest.json", manifest)

    # A5 · 2026-08-06: plate vs master — never auto master_lock (leaf)
    from final.stages_official_finalize import apply_official_final_classification

    official_final = apply_official_final_classification(
        root=root,
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        report=report,
        report_path=report_path,
        manifest=manifest,
        final_path=final_path,
        technical_qa=technical_qa,
        bgm_source_receipt=bgm_source_receipt,
        build_final_film_manifest_entry=build_final_film_manifest_entry,
        write_json=write_json,
        utc_now=utc_now,
        log=log,
    )

    return {
        "ok": True,
        "output": str(final_path),
        "duration_sec": report["duration_sec"],
        "srt": str(srt_path),
        "report": str(report_path),
        "cue_count": len(cues),
        "music_license": license_note,
        "lipsync_shots": lipsync_report,
        "official_final": official_final,
        "bgm_source": bgm_source_receipt,
    }



def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render formal final film with VO + BGM + subs")
    p.add_argument("--root", required=True)
    p.add_argument("--out-name", default="film_final.mp4")
    p.add_argument("--voice", default=None, help="edge voice id or Fish reference_id")
    p.add_argument(
        "--tts-backend",
        default=None,
        choices=["audio_node", "auto", "minimax", "fish", "edge", "external"],
        help="TTS: audio_node uses private Qwen3-TTS; auto prefers external > MiniMax > pinned Fish > edge",
    )
    p.add_argument(
        "--vo-rate", default=None, help='TTS rate e.g. "-5%%" (edge) / maps to Fish speed'
    )
    p.add_argument("--vo-pitch", default=None, help='TTS pitch e.g. "-1Hz" (edge only)')
    p.add_argument("--vo-gain", type=float, default=None, help="Narration mix gain (default 1.15)")
    p.add_argument(
        "--vocal-color-gain",
        type=float,
        default=None,
        help="Independent 娇喘/语助词 track mix gain (0..1.5; default 0 / off; opt-in with voice_tracks.enabled)",
    )
    p.add_argument("--title")
    p.add_argument("--end-title")
    p.add_argument("--title-dur", type=float, default=1.5)
    p.add_argument("--end-dur", type=float, default=1.6)
    p.add_argument(
        "--plate-cards",
        choices=["text", "blank"],
        default="blank",
        help="blank=pad only with no glyphs (default); text is an explicit FFmpeg compatibility override",
    )
    p.add_argument(
        "--sub-lead",
        type=float,
        default=0.0,
        help="Show subtitles this many seconds early (default 0; >0 risks SRT overlap hard-fail)",
    )
    p.add_argument("--sub-min-unit", type=float, default=0.48)
    p.add_argument("--sub-max-unit", type=float, default=1.75)
    p.add_argument("--sub-max-chars", type=int, default=DEFAULT_SUB_MAX_CHARS)
    p.add_argument("--vo-pad", type=float, default=0.12)
    p.add_argument(
        "--vo-fit",
        default=None,
        choices=["atempo", "legacy"],
        help=(
            "slot visual_fit: atempo=VO speed to plate (cn three-axis, default); "
            "legacy=pad/trim only and may stretch video to VO"
        ),
    )
    p.add_argument(
        "--transition-sec",
        type=float,
        default=None,
        help=f"Inter-shot xfade/acrossfade seconds (default {DEFAULT_TRANSITION_SEC}; 0=hard cut)",
    )
    p.add_argument("--music", help="Optional external music file (overrides local templates)")
    p.add_argument(
        "--music-license",
        help="License note for --music or local template (or put audio/*.license.txt)",
    )
    p.add_argument(
        "--music-template",
        default=None,
        choices=["off", "auto", "on", "timeline", "approved_library"],
        help=(
            "Local BGM: auto=one film bed; on=require one local bed; off=procedural; "
            "timeline=one film-local template per cue; approved_library=shared human-approved "
            "catalog per cue (missing mood blocks render)"
        ),
    )
    p.add_argument(
        "--music-volume",
        type=float,
        default=DEFAULT_MUSIC_VOLUME,
        help="BGM mix gain (once only). Dual-track: ~0.28-0.38 so BGM is audible under VO",
    )
    p.add_argument(
        "--native-audio-volume",
        type=float,
        default=None,
        help="Mix gain for original generated clip audio (0..1; default film-spec or 0.72; primary video sound)",
    )
    p.add_argument(
        "--music-mood",
        default="rnb",
        choices=["playful", "dark", "warm", "rnb", "sensual", "soul"],
        help="BGM mood; rnb/sensual/soul = seductive late-night R&B/Soul (色气默认，勿用 dark)",
    )
    p.add_argument(
        "--music-seed",
        type=int,
        default=None,
        help="Procedural BGM RNG seed (omit = stable hash of title+mood; change to hear a new take)",
    )
    p.add_argument(
        "--sidechain-threshold",
        type=float,
        help="VO→BGM sidechain threshold (default: rnb 0.065 / other 0.08)",
    )
    p.add_argument(
        "--sidechain-ratio",
        type=float,
        help="VO→BGM sidechain ratio (default: rnb 3.8 / other 3.5)",
    )
    p.add_argument(
        "--sidechain-attack",
        type=float,
        default=None,
        help="Sidechain attack ms (default: rnb 15 / other 20)",
    )
    p.add_argument(
        "--sidechain-release",
        type=float,
        help="Sidechain release ms — higher = BGM returns slower in VO pauses (rnb default 880)",
    )
    p.add_argument(
        "--loudnorm",
        default=None,
        choices=["off", "auto", "on"],
        help="Normalize mixed loudness: auto=only if too loud/quiet (default); on=always; off=never",
    )
    p.add_argument(
        "--target-lufs",
        type=float,
        default=None,
        help="loudnorm target integrated LUFS (default -16 shortform)",
    )
    p.add_argument(
        "--lipsync",
        default="off",
        choices=["off"],
        help="Post lipsync removed (v2.40); only off. Dialogue = native Grok/H3 audio.",
    )
    p.add_argument(
        "--allow-loop-risk",
        action="store_true",
        help="Allow final even when VO would stream_loop short plates (discouraged)",
    )
    p.add_argument(
        "--render-timeout",
        type=float,
        default=1800.0,
        help=(
            "Total wall-clock budget (seconds) for render_final. Exceeding it raises a clean "
            "RenderTimeoutError instead of hanging (假死). 0 disables the guard. "
            "Per-subprocess ffmpeg calls still honor AIFILM_FFMPEG_TIMEOUT."
        ),
    )
    p.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Record plate honesty only (CLI also skips preflight); marks OFFICIAL_FINAL_PLATE",
    )
    p.add_argument(
        "--skip-heat-gate",
        action="store_true",
        help="Record plate honesty when heat final gate was skipped upstream",
    )
    p.add_argument(
        "--subs",
        default="off",
        choices=["burn", "off"],
        help="off=SRT only (default; HyperFrames owns visible captions); burn is an explicit FFmpeg compatibility override",
    )
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument(
        "--export-stems",
        action="store_true",
        help="Export isolated narration, BGM, native, SFX, scene-sound, and ambience stems",
    )
    p.add_argument(
        "--ambience-volume",
        type=float,
        default=1.0,
        help="Independent ambience stem gain from 0.0 to 2.0 (default: 1.0)",
    )
    p.add_argument(
        "--mute-ambience",
        action="store_true",
        help="Mute the ambience stem while preserving all other stems",
    )
    p.add_argument("--fps", type=int)
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume valid shot stretch/lipsync checkpoints; stale or missing outputs rerun",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Clear shot checkpoints before rendering",
    )
    args = p.parse_args(argv)
    root_for_timeout = Path(getattr(args, "root", ".")).expanduser().resolve()
    try:
        # Explicit --music still requires license text OR sidecar (checked inside resolve)
        if args.music and not (args.music_license and args.music_license.strip()):
            # allow if sidecar will supply; soft check path exists near file
            p = Path(args.music).expanduser()
            side_ok = False
            try:
                from sound_plan import _license_sidecar_for

                side_ok = bool(_license_sidecar_for(p) if p.is_file() else False)
            except Exception:
                side_ok = False
            if not side_ok:
                raise RenderError(
                    "--music requires --music-license (or a sidecar "
                    f"{p.stem}.license.txt next to the file)"
                )
        result = _run_with_watchdog(lambda: render_final(args), timeout=args.render_timeout)
        try:
            from final.heartbeat import write_final_heartbeat

            write_final_heartbeat(root_for_timeout, stage="done", detail="ok")
        except Exception:
            pass
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except subprocess.TimeoutExpired as exc:
        from util import read_json as _read_json

        stage = "unknown"
        next_cmd = None
        try:
            hb = _read_json(root_for_timeout / "receipts" / "final-heartbeat.json") or {}
            stage = str(hb.get("stage") or "unknown")
        except Exception:
            pass
        try:
            from final.heartbeat import write_final_timeout_receipt

            rec_path = write_final_timeout_receipt(
                root_for_timeout,
                stage=stage,
                timeout_sec=exc.timeout,
                error=str(exc),
            )
            next_cmd = (_read_json(rec_path) or {}).get("next_cmd")
        except Exception:
            next_cmd = (
                f'aifilm final --root "{root_for_timeout}" --lipsync off '
                f"# timed out stage={stage}; raise AIFILM_FFMPEG_TIMEOUT"
            )
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"final timed out at stage={stage}: {exc}",
                    "stage": stage,
                    "timeout_sec": exc.timeout,
                    "next_cmd": next_cmd,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except (RenderError, subprocess.CalledProcessError, ValueError) as exc:
        err = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            err = (exc.stderr or exc.stdout or str(exc))[:2000]
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
