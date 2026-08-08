#!/usr/bin/env python3
"""Render a formal final film: edge-tts VO + BGM + FFmpeg plate.

Post lipsync removed (v2.40): dialogue uses native clip audio (prefer_native).
``--lipsync`` must stay ``off``. See references/lipsync.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from audio_timeline import caption_bindings as timeline_caption_bindings
from dialogue_broll import validate_broll_visual_review, write_broll_edit_report
from edit_policy import (
    DEFAULT_TRANSITION_SEC,
)
from logger import log
from media_qa import approved_clip_record
from runtime_policy import sha256
from sound_plan import (
    SoundPlanError,
    build_mood_timeline,
    resolve_music_template,
)
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


def extract_native_audio(*args: Any, **kwargs: Any) -> Path | None:
    """Hard-compat stub for build_shot_audio_stems (native via register-clip receipts)."""
    return None


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
    _paths = ctx.paths
    out_dir = ctx.out_dir
    final_path = ctx.final_path
    manifest = ctx.manifest
    spec = ctx.spec
    scene_sound_report = ctx.scene_sound_report
    _timeline = ctx.timeline
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
    _lipsync_mode = ctx.lipsync_mode
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
    _stretched = _pic["stretched"]
    lipsync_report = _pic["lipsync_report"]
    broll_edit_report = _pic["broll_edit_report"]
    broll_edit_report_sha256 = _pic["broll_edit_report_sha256"]
    title_text = _pic["title_text"]
    _end_text = _pic["end_text"]
    _title_mp4 = _pic["title_mp4"]
    _end_mp4 = _pic["end_mp4"]
    title_dur = _pic["title_dur"]
    end_dur = _pic["end_dur"]
    silent = _pic["silent"]
    transition_sec = _pic["transition_sec"]
    story_intents = _pic["story_intents"]
    default_intent = _pic["default_intent"]
    full_join_intents = _pic["full_join_intents"]
    _full_join_styles = _pic["full_join_styles"]
    _full_join_use_ts = _pic["full_join_use_ts"]
    _transition_style = _pic["transition_style"]
    xfade_plan = _pic["xfade_plan"]

    # 5) Narration + native tracks (leaf: final.stages_voice_timeline)
    from final.stages_voice_timeline import build_narration_and_native_tracks

    _vo = build_narration_and_native_tracks(
        work=work,
        audio_dir=audio_dir,
        shot_audio=shot_audio,
        title_dur=float(title_dur),
        end_dur=float(end_dur),
        transition_sec=float(transition_sec),
        xfade_plan=xfade_plan,
        full_join_intents=full_join_intents,
        silence_wav=silence_wav,
    )
    voice_cat = _vo["voice_cat"]
    afade_plan = _vo["afade_plan"]
    total_dur = _vo["total_dur"]
    native_track = _vo["native_track"]
    active_transition = _vo["active_transition"]
    _audio_join_intents = _vo["audio_join_intents"]
    _segs_durs = _vo["segs_durs"]

    # 6a) Audio prep: spotting / timeline / scene stems (leaf: final.stages_audio_prep)
    from final.stages_audio_prep import prepare_audio_mix_context

    _prep = prepare_audio_mix_context(
        root=root,
        work=work,
        audio_dir=audio_dir,
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        shots=shots,
        shot_audio=shot_audio,
        mood=mood,
        vo_gain=float(vo_gain),
        film_vocal_color_gain=float(film_vocal_color_gain),
        native_audio_volume=float(native_audio_volume),
        voice_policy=voice_policy if isinstance(voice_policy, dict) else {},
        scene_sound_report=scene_sound_report if isinstance(scene_sound_report, dict) else {},
        title_dur=float(title_dur),
        end_dur=float(end_dur),
        active_transition=float(active_transition),
        story_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent,
        total_dur=float(total_dur),
        voice_cat=voice_cat,
        silence_wav=silence_wav,
        sound_cues_to_sfx_kinds=sound_cues_to_sfx_kinds,
    )
    music_path = _prep["music_path"]
    mix_spotting = _prep["mix_spotting"]
    shot_start_map = _prep["shot_start_map"]
    shot_end_map = _prep["shot_end_map"]
    _shot_duration_map = _prep["shot_duration_map"]
    audio_timeline_path = _prep["audio_timeline_path"]
    formal_timeline = _prep["formal_timeline"]
    formal_silence_windows = _prep["formal_silence_windows"]
    _event_voice_stem = _prep["event_voice_stem"]
    use_event_tts = _prep["use_event_tts"]
    voice_cat = _prep["voice_cat"]
    scene_sound_path = _prep["scene_sound_path"]
    ambience_path = _prep["ambience_path"]
    _scene_sound = _prep["scene_sound"]
    ambience_volume = _prep["ambience_volume"]
    sound_plan = _prep["sound_plan"]
    shot_dicts = _prep["shot_dicts"]
    color_track = _prep["color_track"]
    _apply_spotting_and_convert_to_stereo = _prep["apply_spotting"]

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
    _music_resolved = bed["music_resolved"]
    bgm_source_receipt = bed["bgm_source_receipt"]
    mood = bed["mood"]

    # 7) Dual-track mix + loudnorm (leaf: final.stages_dual_mix)
    from final.stages_dual_mix import run_dual_track_mix_stage

    _mix = run_dual_track_mix_stage(
        root=root,
        work=work,
        audio_dir=audio_dir,
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        shot_audio=shot_audio,
        mood=mood,
        vo_gain=float(vo_gain),
        native_audio_volume=float(native_audio_volume),
        music_path=music_path,
        voice_cat=voice_cat,
        native_track=native_track,
        sfx_stereo_path=sfx_stereo_path,
        scene_sound_path=scene_sound_path,
        ambience_path=ambience_path,
        ambience_volume=float(ambience_volume),
        color_track=color_track,
        mix_spotting=mix_spotting,
        sound_plan=sound_plan if isinstance(sound_plan, dict) else None,
        formal_silence_windows=formal_silence_windows,
        formal_timeline=formal_timeline,
        run=run,
        write_final_mix_partial_receipt=write_final_mix_partial_receipt,
        summarize_bgm_response=summarize_bgm_response,
        build_music_mix_review=build_music_mix_review,
        probe_mixed_loudness=probe_mixed_loudness,
        sha256=sha256,
        heartbeat=_hb,
        sample_rate_default=SR,
    )
    mixed = _mix["mixed"]
    mix_spotting = _mix["mix_spotting"]
    music_vol = _mix["music_vol"]
    filters_help = _mix["filters_help"]
    preserved_native_shots = _mix["preserved_native_shots"]
    suppressed_native_shots = _mix["suppressed_native_shots"]
    _use_color = _mix["use_color"]
    _mix_sample_rate = _mix["mix_sample_rate"]

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
    _event_caption_bindings = _subs["event_caption_bindings"]
    srt_path = _subs["srt_path"]
    srt_stable = _subs["srt_stable"]
    video_subbed = _subs["video_subbed"]
    subs_mode = _subs["subs_mode"]

    # 9) Mux final + verify streams (leaf: final.stages_mux_manifest)
    from final.stages_mux_manifest import mux_final_mp4, verify_final_streams

    mux_final_mp4(video_subbed=video_subbed, mixed=mixed, final_path=final_path, run=run)
    _streams = verify_final_streams(
        final_path=final_path,
        audio_timeline_v1=bool(spec.get("audio_timeline_v1", False)),
        run=run,
        render_error_cls=RenderError,
    )

    # 9b) Technical delivery report (leaf: final.stages_delivery_report)
    # timeline_caption_bindings: module-level import only — a local re-import here
    # made Python treat the name as function-local and raised UnboundLocalError at
    # stages_subs (used earlier in the same function).
    from final.stages_delivery_report import write_technical_delivery

    _del = write_technical_delivery(
        root=root,
        out_dir=out_dir,
        audio_dir=audio_dir,
        final_path=final_path,
        args=args,
        spec=spec if isinstance(spec, dict) else {},
        manifest=manifest if isinstance(manifest, dict) else {},
        film_tl=film_tl,
        title_text=str(title_text),
        width=width,
        height=height,
        fps=fps,
        vo_mode=vo_mode,
        voice=voice,
        transition_sec=float(transition_sec),
        active_transition=float(active_transition),
        story_intents=list(story_intents) if story_intents is not None else None,
        full_join_intents=full_join_intents,
        default_intent=default_intent,
        xfade_plan=xfade_plan,
        afade_plan=afade_plan,
        mix_spotting=mix_spotting,
        broll_edit_report=broll_edit_report,
        broll_edit_report_sha256=broll_edit_report_sha256,
        tts_backend=str(tts_backend),
        cast_tts_backends=cast_tts_backends if isinstance(cast_tts_backends, dict) else {},
        tts_info=tts_info if isinstance(tts_info, dict) else {},
        shot_audio=shot_audio,
        voice_cat=voice_cat,
        music_path=music_path,
        license_note=str(license_note),
        music_vol=float(music_vol),
        filters_help=str(filters_help or ""),
        mood=mood,
        bgm_source_receipt=bgm_source_receipt,
        native_track=native_track,
        native_audio_volume=float(native_audio_volume),
        preserved_native_shots=preserved_native_shots,
        suppressed_native_shots=suppressed_native_shots,
        audio_timeline_path=audio_timeline_path,
        formal_timeline=formal_timeline,
        srt_path=srt_path,
        srt_stable=srt_stable,
        cues=cues,
        subs_mode=subs_mode,
        lipsync_report=lipsync_report,
        sha256=sha256,
        timeline_caption_bindings=timeline_caption_bindings,
    )
    report = _del["report"]
    report_path = _del["report_path"]
    technical_qa = _del["technical_qa"]
    manifest = _del["manifest"]

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
            except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
