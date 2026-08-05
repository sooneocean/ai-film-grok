#!/usr/bin/env python3
"""Render a formal final film: edge-tts VO + optional lip-sync + BGM + FFmpeg plate.

Adapted from ai-film-codex postproduction (render_motion_film / make_v6 patterns)
for ai-film-grok local manifests and Grok I2V clips.

Lip-sync stage (optional): after VO, retime talking faces with MuseTalk/Wav2Lip/external
so mouth matches 口白 — see references/lipsync.md.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
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
    build_acrossfade_filter_graph,
    build_xfade_filter_graph,
    expand_story_join_intents,
    expand_story_join_styles,
    film_segment_timeline,
    normalize_transition_sec,
    plan_stretch,
)
from event_voice_stem import EventVoiceStemError, render_event_voice_stem
from film_spec import FilmSpecError, validate_film_spec
from logger import log
from media_qa import MediaQAError, analyze_media, approved_clip_record
from narrative_timeline import (
    NarrativeTimelineError,
    _is_non_vo_coverage_shot,
    validate_sfx_scene_bindings,
)
from narrative_timeline import (
    validate_linear_narration as _validate_linear_narration,
)
from PIL import Image, ImageDraw, ImageFont
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
    apply_mute_windows_to_samples,
    apply_sfx_accents_to_samples,
    build_mood_timeline,
    expand_sound_events,
    inject_auto_sfx_if_empty,
    resolve_loudnorm,
    resolve_music_template,
    resolve_sidechain,
    should_apply_loudnorm,
    sidechain_filter_fragment,
    validate_audio_tracks_contract,
)
from transition_ops import TransitionOperationError, bind_transition_operations_to_timeline
from util import run_ffmpeg, utc_now, write_json
from util.subprocess import run as util_run

# local sibling import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from lipsync_backend import enforce_dialogue_lipsync, lipsync_one, should_lipsync_shot
    from lipsync_backend import probe as lipsync_probe
except ImportError:  # pragma: no cover
    lipsync_one = None  # type: ignore
    should_lipsync_shot = None  # type: ignore
    enforce_dialogue_lipsync = None  # type: ignore
    lipsync_probe = None  # type: ignore

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
from final.errors import RenderError  # noqa: E402
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
from final.voice import (  # noqa: E402, F401
    DEFAULT_VOICE,
    HEROINE_ZH_VOICE,
    PARTNER_ZH_VOICE,
    STORYTELLER_VOICE,
    _HEROINE_SPEAKERS,
    _NARRATOR_SPEAKERS,
    _PARTNER_SPEAKERS,
    _locked_voice_role,
    tts_backend_for_shot,
    validate_voice_language_locks,
    voice_for_shot,
)
from final.media_ops import (  # noqa: E402, F401
    apply_dialogue_broll_visual,
    concat_audio_segments,
    concat_videos,
    pdur,
    run,
    stable_path_for_ffmpeg_filter,
    stretch_clip,
)

from final.enhance import (  # noqa: E402, F401
    build_post_enhancement_vf_chain,
    resolve_subtitle_mode,
)
from final.native_audio import (  # noqa: E402, F401
    DEFAULT_NATIVE_AUDIO_VOLUME,
    NATIVE_AUDIO_GAIN_MAX,
    NATIVE_AUDIO_GAIN_MIN,
    NATIVE_AUDIO_TARGET_DB,
    native_dialogue_replaced_by_post_tts,
    primary_native_shot_ids,
    resolve_native_audio_gain,
    resolve_native_audio_volume,
)
from final.cards import (  # noqa: E402, F401
    FONT_CANDIDATES,
    _wrap_title_lines,
    mkcard_video,
    resolve_font as _resolve_font_from_cards,
    sub_png,
)


def resolve_font() -> str:
    """Resolve Chinese-capable font using this module's FONT_CANDIDATES (hard-compat patchable)."""
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return path
    raise RenderError("No Chinese-capable system font found")


# 中文女声优先：旁白是主叙事，必须压过 BGM
# TTS 质量与稳定声线分开选择；跨服务商降级必须显式开启。
DEFAULT_MUSIC_VOLUME = 0.48  # 略降 BGM，旁白更贴耳、节奏更干净
DEFAULT_BGM_GEN_AMP = 0.22  # 程序化 BGM 生成响度（固定，勿再乘 music_volume）
DEFAULT_VO_GAIN = 1.32  # 旁白增益：清晰压过环境音与 BGM（星声 lesson 略抬）
DEFAULT_VOCAL_COLOR_GAIN = 0.0  # 2026-07-21: 语助轨默认关闭；成片以 nar+BGM 主导
DEFAULT_VO_RATE = "+0%"  # 默认不拖腔；快节奏色气短片可用 +5%~+8%（禁 -3%+slot 叠拖）
DEFAULT_VO_PITCH = "+0Hz"
SR = 44100
# 9:16 竖屏：一句一卡；过长句按逗号拆开，阅读更轻松
DEFAULT_SUB_MAX_CHARS = 12  # phrase-sized cue; long nar always splits at ，/。


def read_json(path: Path) -> dict[str, Any]:
    """Strict JSON — util.require_json_fnv (FileNotFoundError / ValueError)."""
    from util import require_json_fnv

    return require_json_fnv(path)


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

from final.tts_tracks import (  # noqa: E402, F401
    DEFAULT_VOCAL_COLOR_GAIN as _TTS_DEFAULT_VOCAL_COLOR_GAIN,
    SR as _TTS_SR,
    build_native_track,
    build_vocal_color_track,
    tts_edge,
    tts_to_wav,
)


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


def render_final(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    try:
        paths = resolve_render_paths(root, args.out_name)
    except RenderWorkspaceError as exc:
        raise RenderError(str(exc)) from exc
    out_dir = paths["out_dir"]
    final_path = paths["final"]
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RenderError("ffmpeg/ffprobe required")

    if tts_synthesize is None:
        raise RenderError("tts_backend.py missing next to render_final.py")

    manifest = read_json(root / "manifest.json")
    spec = read_json(root / "film-spec.json")
    scene_sound_report = reconcile_scene_sound(root, write=True)
    if bool(spec.get("audio_timeline_v1", False)) and scene_sound_report["status"] == "blocked":
        raise RenderError(
            "scene-sound required assets missing: "
            + ", ".join(scene_sound_report["blocking_shot_ids"])
        )
    audio_contract = validate_audio_tracks_contract(spec)
    for warning in audio_contract.get("warnings") or []:
        log(f"audio contract warning: {warning}")
    # Hard gate: long VO on short plates → stream_loop (boring). Split nars first.
    from production_gates import ProductionGateError, assert_no_loop_risk

    try:
        assert_no_loop_risk(root, force=bool(getattr(args, "allow_loop_risk", False)))
    except ProductionGateError as exc:
        raise RenderError(str(exc)) from exc
    timeline = read_json(root / "timeline.json") if (root / "timeline.json").is_file() else {}
    width = int(args.width or timeline.get("width") or manifest.get("width") or 720)
    height = int(args.height or timeline.get("height") or manifest.get("height") or 1280)
    fps = int(args.fps or timeline.get("fps") or 30)
    # Film-spec may override VO strategy
    vo_mode = str(spec.get("vo_mode") or "storyteller").lower()
    # 默认中文女声（晓晓 edge 兜底）；Fish 时 voice 可填 FISH voice id
    voice = (
        args.voice
        or spec.get("vo_voice")
        or (STORYTELLER_VOICE if vo_mode in ("storyteller", "hybrid") else DEFAULT_VOICE)
    )
    # 一角一声：film-spec.cast_voices = {"storyteller": "zh-CN-XiaoxiaoNeural", "heroine": "..."}
    cast_voices_raw = spec.get("cast_voices") or {}
    cast_voices: dict[str, str] = {}
    if isinstance(cast_voices_raw, dict):
        for k, v in cast_voices_raw.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                cast_voices[k.strip()] = v.strip()
    # Chinese-only cast defaults (Japanese retired 2026-08-04)
    cast_voices.setdefault("heroine", HEROINE_ZH_VOICE)
    cast_voices.setdefault("partner", PARTNER_ZH_VOICE)
    cast_voices.setdefault("male_hero", PARTNER_ZH_VOICE)
    cast_voices.setdefault("storyteller", STORYTELLER_VOICE)
    # Strip legacy ja-JP locks so Chinese TTS never inherits Japanese voice ids.
    for _role, _vid in list(cast_voices.items()):
        if isinstance(_vid, str) and (_vid.startswith("ja-JP-") or _vid.startswith("ja-")):
            if _role in {"heroine"}:
                cast_voices[_role] = HEROINE_ZH_VOICE
            elif _role in {"partner", "male_hero", "hero"}:
                cast_voices[_role] = PARTNER_ZH_VOICE
            else:
                cast_voices[_role] = STORYTELLER_VOICE
    vo_rate = str(getattr(args, "vo_rate", None) or spec.get("vo_rate") or DEFAULT_VO_RATE)
    vo_pitch = str(getattr(args, "vo_pitch", None) or spec.get("vo_pitch") or DEFAULT_VO_PITCH)
    vo_tts_vol = str(getattr(args, "vo_tts_volume", None) or spec.get("vo_tts_volume") or "+0%")
    tts_backend = (
        getattr(args, "tts_backend", None)
        or spec.get("tts_backend")
        or os.environ.get("AIFILM_TTS_BACKEND")
        or "auto"
    )
    tts_allow_network_fallback = bool(spec.get("tts_allow_network_fallback", False))
    cast_tts_backends_raw = spec.get("cast_tts_backends") or {}
    cast_tts_backends: dict[str, str] = {}
    if not isinstance(cast_tts_backends_raw, dict):
        raise RenderError("cast_tts_backends must be an object when configured")
    for role, provider in cast_tts_backends_raw.items():
        if (
            isinstance(role, str)
            and isinstance(provider, str)
            and role.strip()
            and provider.strip()
        ):
            cast_tts_backends[role.strip()] = provider.strip().lower()
    raw_gain = getattr(args, "vo_gain", None)
    if raw_gain is None:
        raw_gain = spec.get("vo_gain")
    vo_gain = float(raw_gain if raw_gain is not None else DEFAULT_VO_GAIN)
    # Multi-track voice policy (nar vs 娇喘语助 vs native)
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
        film_vocal_color_gain = float(
            raw_color_gain if raw_color_gain is not None else DEFAULT_VOCAL_COLOR_GAIN
        )
    except (TypeError, ValueError):
        film_vocal_color_gain = DEFAULT_VOCAL_COLOR_GAIN
    film_vocal_color_gain = max(0.0, min(1.5, film_vocal_color_gain))
    # 色气 / storyteller → seductive R&B by default；音乐必须远低于旁白
    mood = args.music_mood or ("rnb" if vo_mode in ("storyteller", "hybrid") else "playful")
    lipsync_mode = (getattr(args, "lipsync", None) or "off").lower()
    # Storyteller: never lipsync unless user forced --lipsync require
    if vo_mode == "storyteller" and lipsync_mode not in (
        "require",
        "wav2lip",
        "external",
    ):
        if lipsync_mode != "off":
            log("storyteller mode → force lipsync off")
        lipsync_mode = "off"
    tts_info = tts_probe() if tts_probe else {}
    log(
        f"vo_mode={vo_mode} tts={tts_backend}->{tts_info.get('active')} voice={voice} "
        f"rate={vo_rate} pitch={vo_pitch} vo_gain={vo_gain} music_vol={args.music_volume} "
        f"mood={mood} lipsync={lipsync_mode}"
    )
    font_path = resolve_font()

    shots = flatten_shots(spec, film_root=root)
    if enforce_dialogue_lipsync is None:
        raise RenderError("dialogue lip-sync gate is unavailable")
    try:
        lipsync_mode = enforce_dialogue_lipsync(
            vo_mode=vo_mode,
            shots=shots,
            requested=lipsync_mode,
        )
    except Exception as exc:
        raise RenderError(str(exc)) from exc
    try:
        # The validator runs in flatten_shots; this makes the renderer's TTS
        # selection explicit and refuses ambiguous multi-turn shots.
        shot_voice_cues = {str(shot["id"]): primary_voice_cue(shot) for shot in shots}
    except AudioCueError as exc:
        raise RenderError(str(exc)) from exc
    clips_map = manifest.get("clips") or {}
    try:
        prepare_render_workspace(paths)
    except RenderWorkspaceError as exc:
        raise RenderError(str(exc)) from exc
    clips_dir = paths["clips_dir"]
    audio_dir = paths["audio_dir"]
    native_dir = paths["native_dir"]
    keyframes_dir = paths["keyframes_dir"]
    work = paths["work"]
    overlays_dir = work / "overlays"
    checkpoint = CheckpointManager(root)
    if bool(getattr(args, "force", False)):
        checkpoint.clear()
    resume = bool(getattr(args, "resume", False))

    dialogue_spoken_lang = str(
        spec.get("dialogue_spoken_lang")
        or (spec.get("voice_policy") or {}).get("dialogue_spoken_lang")
        or "zh"
    )
    if dialogue_spoken_lang.strip().lower() in {"ja", "jp", "japanese"}:
        raise RenderError(
            "Japanese dialogue is retired; set dialogue_spoken_lang=zh (Chinese-only product)"
        )
    dialogue_spoken_lang = "zh"
    narration_spoken_lang = str(
        spec.get("narration_spoken_lang")
        or (spec.get("voice_policy") or {}).get("narration_spoken_lang")
        or "zh"
    )

    # 1) Per-shot TTS
    validate_voice_language_locks(shots, dialogue_spoken_lang=dialogue_spoken_lang)
    validate_linear_narration(
        shots,
        vo_mode=vo_mode,
        dialogue_spoken_lang=dialogue_spoken_lang,
        narration_spoken_lang=narration_spoken_lang,
    )
    shot_audio: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        sid = shot["id"]
        rec = clips_map.get(sid)
        if not approved_clip_record(rec):
            raise RenderError(
                f"Clip {sid} lacks endpoint, identity, motion, review-note, or decode QA evidence"
            )
        try:
            clip_path = safe_existing_file(clips_dir, rec["path"], field=f"clip path for {sid}")
        except (KeyError, SecurityPolicyError) as exc:
            raise RenderError(str(exc)) from exc
        broll_sources: list[dict[str, Any]] = []
        for entry in shot.get("dialogue_broll") or []:
            if not isinstance(entry, dict):
                continue
            bid = str(entry.get("id") or "")
            broll_rec = clips_map.get(bid)
            if not approved_clip_record(broll_rec):
                raise RenderError(
                    f"Dialogue B-roll {bid} lacks approved checksum, review, identity, motion, or decode QA evidence"
                )
            try:
                broll_clip = safe_existing_file(
                    clips_dir, broll_rec["path"], field=f"B-roll clip path for {bid}"
                )
            except (KeyError, SecurityPolicyError) as exc:
                raise RenderError(str(exc)) from exc
            recorded_sha256 = str(broll_rec.get("sha256") or "")
            actual_sha256 = sha256(broll_clip)
            if not recorded_sha256 or recorded_sha256 != actual_sha256:
                raise RenderError(f"Dialogue B-roll {bid} source SHA-256 is missing or mismatched")
            visual_review = validate_broll_visual_review(
                broll_rec.get("broll_visual_review"),
                kind=str(entry.get("kind") or ""),
                expected_sha256=actual_sha256,
            )
            if not visual_review["ok"]:
                raise RenderError(
                    f"Dialogue B-roll {bid} visual review blocked: {visual_review['reason']}"
                )
            broll_sources.append({**entry, "clip": broll_clip})
        native_audio = None
        native_audio_audible: bool | None = None
        native_audio_gain = 1.0
        native_record = rec.get("native_audio")
        if isinstance(native_record, dict):
            try:
                native_audio = safe_existing_file(
                    native_dir, native_record["path"], field=f"native audio path for {sid}"
                )
            except (KeyError, SecurityPolicyError) as exc:
                raise RenderError(str(exc)) from exc
            if native_record.get("sha256") != sha256(native_audio):
                raise RenderError(f"Native audio fingerprint changed for {sid}")
            recorded_audible = native_record.get("audible")
            native_audio_audible = recorded_audible if isinstance(recorded_audible, bool) else None
            native_audio_gain = resolve_native_audio_gain(native_record)
        native_dialogue_replaced = (
            native_audio is not None and native_dialogue_replaced_by_post_tts(shot)
        )
        caption_lang = str(
            spec.get("caption_lang") or (spec.get("voice_policy") or {}).get("caption_lang") or "zh"
        )
        voice_cue = shot_voice_cues.get(str(sid))
        try:
            text = strict_tts_text(shot, strict=bool(spec.get("audio_cues_strict")))
        except AudioCueError as exc:
            raise RenderError(str(exc)) from exc
        if text is None:
            text = spoken_text_for_shot(
                shot,
                dialogue_spoken_lang=dialogue_spoken_lang,
                narration_spoken_lang=narration_spoken_lang,
                vo_mode=vo_mode,
            )
        caption_text = caption_text_for_shot(shot, caption_lang=caption_lang) or text
        # dialogue_drama coverage (reaction / action_cover / silence without voice cue)
        # may legitimately carry no TTS line — plate is ambience/foley only.
        non_vo_coverage = _is_non_vo_coverage_shot(shot) and not text
        max_chars = int(
            getattr(args, "sub_max_chars", DEFAULT_SUB_MAX_CHARS) or DEFAULT_SUB_MAX_CHARS
        )
        # Subtitles + TTS: Chinese-only product path
        units = split_units(caption_text, max_len=max_chars) if caption_text else []
        try:
            mp3 = safe_output_path(
                audio_dir, f"{sid}_vo.mp3", suffixes={".mp3"}, field=f"VO output for {sid}"
            )
            safe_output_path(
                audio_dir, f"{sid}_vo.wav", suffixes={".wav"}, field=f"VO WAV output for {sid}"
            )
        except SecurityPolicyError as exc:
            raise RenderError(str(exc)) from exc
        if non_vo_coverage:
            try:
                plate_slot = float(shot.get("duration_sec") or 0.0)
            except (TypeError, ValueError):
                plate_slot = 0.0
            if plate_slot <= 0.05:
                plate_slot = 1.0
            silent_wav = work / f"vo_silent_{i:02d}_{sid}.wav"
            silence_wav(silent_wav, plate_slot)
            # keep mp3 companion for downstream path expectations (empty AAC ok via ffmpeg)
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(silent_wav),
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "4",
                    str(mp3),
                ]
            )
            wav = silent_wav
            dur = plate_slot
            tts_meta = {
                "backend": "silence",
                "voice": "none",
                "note": "non_vo_coverage",
                "duration_sec": plate_slot,
            }
            text = ""
            caption_text = ""
            units = []
            shot_voice = "none"
            shot_tts_backend = "silence"
            log(f"silence VO {sid}: coverage plate {plate_slot:.2f}s (no TTS)")
            color_wav = None
            color_dur = 0.0
            color_meta = None
            color_payload = {}
            color_text = ""
            color_gain = 0.0
        else:
            if not text:
                raise RenderError(
                    f"Shot {sid} has no spoken text for VO "
                    f"(need Chinese nar/dialogue/caption_text or voice.spoken_text)"
                )
            log(f"TTS {sid}: {text[:40]}...")
            voice_source = {**shot, "speaker": voice_cue.get("speaker")} if voice_cue else shot
            shot_voice = voice_for_shot(
                voice_source,
                default_voice=voice,
                cast_voices=cast_voices,
                vo_mode=vo_mode,
                dialogue_spoken_lang=dialogue_spoken_lang,
            )
            shot_tts_backend = tts_backend_for_shot(
                shot,
                default_backend=str(tts_backend),
                cast_tts_backends=cast_tts_backends,
            )
            wav, dur, tts_meta = tts_to_wav(
                text,
                mp3,
                shot_voice,
                rate=vo_rate,
                volume=vo_tts_vol,
                pitch=vo_pitch,
                backend=None if shot_tts_backend == "auto" else shot_tts_backend,
                allow_network_fallback=tts_allow_network_fallback,
                usage_root=root,
                shot_id=sid,
                performance=(
                    voice_cue.get("performance")
                    if voice_cue and isinstance(voice_cue.get("performance"), dict)
                    else normalize_performance_cue(
                        shot.get("performance_cue"), tone_tags=shot.get("tone_tags")
                    )
                    if normalize_performance_cue is not None
                    else None
                ),
            )
            log(
                f"  tts backend={tts_meta.get('backend')} voice={tts_meta.get('voice') or shot_voice} "
                f"dur={dur:.2f}s"
            )
            # Independent 娇喘/语助词 stem (not mixed into nar text)
            color_wav: Path | None = None
            color_dur = 0.0
            color_meta: dict[str, Any] | None = None
            color_payload: dict[str, Any] = {}
        if (
            not non_vo_coverage
            and resolve_shot_vocal_color is not None
            and voice_policy.get("enabled", False)
        ):
            try:
                color_payload = resolve_shot_vocal_color(shot, policy=voice_policy, seed=i * 17)
            except Exception:
                color_payload = {}
        if not non_vo_coverage:
            color_text = str(color_payload.get("text") or "").strip()
            color_gain = float(color_payload.get("gain") or film_vocal_color_gain or 0.0)
        if (not non_vo_coverage) and color_text and color_gain > 0 and film_vocal_color_gain > 0:
            try:
                c_mp3 = safe_output_path(
                    audio_dir,
                    f"{sid}_color.mp3",
                    suffixes={".mp3"},
                    field=f"vocal color output for {sid}",
                )
                safe_output_path(
                    audio_dir,
                    f"{sid}_color.wav",
                    suffixes={".wav"},
                    field=f"vocal color wav for {sid}",
                )
                log(f"  vocal_color TTS {sid}: {color_text[:24]}...")
                color_wav, color_dur, color_meta = tts_to_wav(
                    color_text,
                    c_mp3,
                    shot_voice,
                    rate=str(color_payload.get("rate") or "+0%"),
                    volume=vo_tts_vol,
                    pitch=str(color_payload.get("pitch") or "+2Hz"),
                    backend=None if tts_backend == "auto" else str(tts_backend),
                    allow_network_fallback=tts_allow_network_fallback,
                    usage_root=root,
                    shot_id=f"{sid}-vocal-color",
                    performance=(
                        normalize_performance_cue(
                            shot.get("performance_cue"), tone_tags=shot.get("tone_tags")
                        )
                        if normalize_performance_cue is not None
                        else None
                    ),
                )
                log(f"  vocal_color dur={color_dur:.2f}s gain={color_gain:.2f}")
            except Exception as exc:  # noqa: BLE001 — color is soft layer
                log(f"  vocal_color skip {sid}: {exc}")
                color_wav = None
                color_dur = 0.0
        # Timed voice cues reserve a part of the plate. Pad their stem before
        # mixing so a deliberate opening silence remains silence, not TTS.
        cue_offset = float(voice_cue.get("start_offset_sec") or 0.0) if voice_cue else 0.0
        cue_window = float(voice_cue.get("duration_sec") or 0.0) if voice_cue else 0.0
        if voice_cue and dur > cue_window + 0.03:
            raise RenderError(
                f"{sid} voice cue exceeds its reserved window "
                f"({dur:.2f}s > {cue_window:.2f}s); shorten text or enlarge audio_cues duration"
            )
        # shorter tail — snappier cut to next shot
        # non-vo coverage: silence already matches plate; no VO pad stretch
        if non_vo_coverage:
            pad = 0.0
            target = float(dur)
        else:
            pad = float(getattr(args, "vo_pad", 0.12) or 0.12)
            target = dur + pad
        # visual_fit: "slot" locks to duration_sec; "vo" follows VO length.
        # Wave γ · dialogue_drama / spoken / mid_motion → vo (anti equal-length PPT).
        # See lessons-2026-07-20-action-fluency.md · shortform_no_double_play.
        try:
            from edit_policy import default_visual_fit, resolve_shot_visual_fit

            default_fit = default_visual_fit(spec)
            use_fit = resolve_shot_visual_fit(spec, shot)
        except Exception:
            es = spec.get("edit_strategy") if isinstance(spec.get("edit_strategy"), dict) else {}
            es_mode = str(es.get("mode") or "").strip().lower()
            default_fit = "vo" if es_mode in {"voice_coupled", "punchy"} else "slot"
            visual_fit = str(spec.get("visual_fit") or default_fit).strip().lower()
            shot_fit = str(shot.get("visual_fit") or "").strip().lower()
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            cut_on = str(dsl.get("cut_on") or "").strip().lower()
            if shot_fit in {"vo", "slot"}:
                use_fit = shot_fit
            elif visual_fit == "vo" or cut_on == "mid_motion":
                use_fit = "vo"
            else:
                use_fit = visual_fit if visual_fit in {"vo", "slot"} else default_fit
        visual_fit = str(spec.get("visual_fit") or default_fit).strip().lower()
        try:
            slot = float(shot.get("duration_sec") or 0)
        except (TypeError, ValueError):
            slot = 0.0
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        cut_on = str(dsl.get("cut_on") or "").strip().lower()

        vo_atempo_plan: dict[str, Any] | None = None
        raw_vo_dur = float(dur)
        # vo_fit: atempo (default for slot) | legacy (pad/trim only, stretch video to VO)
        vo_fit = (
            str(spec.get("vo_fit") or getattr(args, "vo_fit", None) or "atempo").strip().lower()
        )
        if vo_fit not in {"atempo", "legacy"}:
            vo_fit = "atempo"

        if voice_cue:
            if slot <= 0:
                raise RenderError(f"{sid} timed voice cue requires duration_sec")
            timed_wav = work / f"vo_timed_{i:02d}_{sid}.wav"
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(wav),
                    "-af",
                    f"adelay={int(round(cue_offset * 1000))}|{int(round(cue_offset * 1000))},apad=pad_dur={slot:.3f},atrim=0:{slot:.3f}",
                    "-ar",
                    str(SR),
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(timed_wav),
                ]
            )
            raw_vo_dur = float(dur)
            wav, dur, target, use_fit = timed_wav, slot, slot, "slot"
            vo_atempo_plan = {
                "mode": "timed_cue",
                "window_sec": cue_window,
                "offset_sec": cue_offset,
            }
        elif use_fit == "slot" and slot > 0 and vo_fit == "atempo":
            # Three-axis: plate = duration_sec; VO atempo to plate; video stretch only to plate
            try:
                from vo_atempo import VoAtempoError, fit_voice_to_plate, plan_vo_atempo

                plate = float(slot)
                plan = plan_vo_atempo(raw_vo_dur, plate)
                if not plan.get("ok"):
                    raise RenderError(
                        f"{sid} vo_atempo: {plan.get('note')} "
                        f"(vo={raw_vo_dur:.2f}s plate={plate:.2f}s). "
                        "Shorten nar, raise duration_sec, or --vo-fit legacy (discouraged)."
                    )
                fitted_wav = work / f"vo_fit_{i:02d}_{sid}.wav"
                vo_atempo_plan = fit_voice_to_plate(
                    wav,
                    fitted_wav,
                    plate,
                    vo_sec=raw_vo_dur,
                    plan=plan,
                    sample_rate=SR,
                )
                wav = fitted_wav
                dur = plate
                target = plate
                log(
                    f"  vo_atempo mode={plan.get('mode')} factor={plan.get('atempo')} "
                    f"raw={raw_vo_dur:.2f}s → plate={plate:.2f}s "
                    f"(video stays plate; no stretch-to-VO)"
                )
            except VoAtempoError as exc:
                raise RenderError(f"{sid} vo_atempo failed: {exc}") from exc
        elif use_fit != "vo" and slot > target:
            # legacy slot: expand timeline to plate without atempo
            target = slot
        # Optional edit handle: only play [in_point, out_point) of source plate
        try:
            out_point = (
                float(shot["out_point_sec"]) if shot.get("out_point_sec") is not None else None
            )
        except (TypeError, ValueError):
            out_point = None
        try:
            in_point = float(shot["in_point_sec"]) if shot.get("in_point_sec") is not None else None
        except (TypeError, ValueError):
            in_point = None
        shot_audio.append(
            {
                "id": sid,
                "text": text,
                "units": units,
                "wav": wav,
                "vo_dur": dur,
                "raw_vo_dur": raw_vo_dur,
                "voice_start_offset_sec": cue_offset,
                "audio_cue": voice_cue,
                "target": target,
                "clip": clip_path,
                "dialogue_broll": broll_sources,
                "title": shot.get("title") or sid,
                "tts": tts_meta,
                "tts_backend_lock": shot_tts_backend,
                "native_audio": native_audio,
                "native_audio_audible": native_audio_audible,
                # The contract is the evidence that native audio contains
                # dialogue. Do not sacrifice unlabelled ambience/foley.
                "native_audio_suppressed_for_tts": native_dialogue_replaced,
                "native_audio_gain": 0.0 if native_dialogue_replaced else native_audio_gain,
                "visual_fit": use_fit,
                "vo_fit": vo_fit if use_fit == "slot" else "n/a",
                "vo_atempo_plan": vo_atempo_plan,
                "out_point_sec": out_point,
                "in_point_sec": in_point,
                "color_wav": color_wav,
                "color_dur": color_dur,
                "color_text": color_text,
                "color_gain": color_gain if color_wav else 0.0,
                "color_offset_sec": color_payload.get("offset_sec", -1.0),
                "color_tts": color_meta,
                "color_source": color_payload.get("source"),
            }
        )

    # 2) Stretch each clip to VO length, then optional lip-sync on talking shots
    lipsync_report: list[dict[str, Any]] = []
    stretched: list[Path] = []
    shots_by_id = {shot.get("id"): shot for shot in shots}
    for i, item in enumerate(shot_audio):
        out = work / f"v_{i:02d}_{item['id']}.mp4"
        shot_meta = shots_by_id.get(item["id"], {})
        beat = shot_meta.get("dramatic_function") if isinstance(shot_meta, dict) else None
        checkpoint_contract = {
            "tts_backend": str(tts_backend),
            "vo_mode": vo_mode,
            "lipsync": lipsync_mode,
            "native_audio_volume": native_audio_volume,
        }
        checkpoint_signature = checkpoint.signature(
            item["clip"],
            target=float(item["target"]),
            width=width,
            height=height,
            fps=fps,
            lipsync=lipsync_mode,
            in_point_sec=item.get("in_point_sec"),
            out_point_sec=item.get("out_point_sec"),
            contract=checkpoint_contract,
        )
        if resume:
            cached = checkpoint.get(item["id"], checkpoint_signature)
            if cached is not None:
                metadata = (
                    cached.get("metadata") if isinstance(cached.get("metadata"), dict) else {}
                )
                item["stretch_plan"] = metadata.get("stretch_plan")
                if metadata.get("target") is not None:
                    item["target"] = float(metadata["target"])
                cached_lipsync = metadata.get("lipsync")
                if isinstance(cached_lipsync, dict) and cached_lipsync.get("id"):
                    lipsync_report.append(cached_lipsync)
                cached_output = Path(str(cached["output"]))
                stretched.append(cached_output)
                log(f"resume {item['id']} -> {cached_output.name}")
                continue
        log(f"stretch {item['id']} -> {item['target']:.2f}s")
        stretch_plan = stretch_clip(
            item["clip"],
            out,
            target=item["target"],
            width=width,
            height=height,
            fps=fps,
            dramatic_function=str(beat) if beat else None,
            in_point_sec=item.get("in_point_sec"),
            out_point_sec=item.get("out_point_sec"),
        )
        item["stretch_plan"] = stretch_plan
        # Keep VO/join clock aligned when stretch clamps target (anti double-play)
        eff = stretch_plan.get("effective_target")
        if eff is not None:
            try:
                eff_f = float(eff)
                if eff_f > 0 and abs(eff_f - float(item["target"])) > 0.04:
                    log(
                        f"  clamp target {item['target']:.2f}s → {eff_f:.2f}s "
                        f"({stretch_plan.get('clamp_reason') or 'stretch'})"
                    )
                    item["target"] = eff_f
                    item["vo_dur"] = min(float(item.get("vo_dur") or eff_f), eff_f)
            except (TypeError, ValueError):
                pass
        log(
            f"  stretch mode={stretch_plan.get('mode')} loops={stretch_plan.get('loops')} "
            f"freeze={stretch_plan.get('freeze_sec')}"
        )

        shot_meta = shots_by_id.get(item["id"], {})
        want_ls = False
        if lipsync_mode != "off" and should_lipsync_shot is not None:
            want_ls = should_lipsync_shot(shot_meta)
        if want_ls and lipsync_one is not None and lipsync_mode != "off":
            ls_out = work / f"v_{i:02d}_{item['id']}_lipsync.mp4"
            backend = "require" if lipsync_mode == "require" else lipsync_mode
            # Only the legacy Wav2Lip path may use a still; RTX dubbing preserves the approved clip.
            face_src = out
            kf = keyframes_dir / f"{item['id']}.jpg"
            if not kf.is_file():
                for ext in (".png", ".jpeg", ".webp"):
                    alt = keyframes_dir / f"{item['id']}{ext}"
                    if alt.is_file():
                        kf = alt
                        break
            if lipsync_mode == "wav2lip" and kf.is_file():
                face_src = kf
            try:
                log(f"lipsync {item['id']} face={face_src.name} backend={backend}...")
                result = lipsync_one(
                    video=face_src,
                    audio=item["wav"],
                    out=ls_out,
                    backend=backend if backend != "require" else "require",
                )
                if result.get("ok") and ls_out.is_file():
                    # Strip embedded audio; final mix uses narration+BGM stems
                    ls_video_only = work / f"v_{i:02d}_{item['id']}_ls_v.mp4"
                    run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(ls_out),
                            "-an",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-crf",
                            "20",
                            "-pix_fmt",
                            "yuv420p",
                            "-t",
                            f"{item['target']:.3f}",
                            str(ls_video_only),
                        ]
                    )
                    out = ls_video_only
                    lipsync_report.append({"id": item["id"], **result})
                else:
                    lipsync_report.append(
                        {
                            "id": item["id"],
                            "ok": False,
                            "skipped": True,
                            "detail": result,
                        }
                    )
                    if lipsync_mode != "auto":
                        raise RenderError(
                            f"lipsync required but skipped for {item['id']}: {result}"
                        )
            except Exception as exc:
                lipsync_report.append({"id": item["id"], "ok": False, "error": str(exc)})
                if lipsync_mode != "auto":
                    raise RenderError(f"lipsync failed for {item['id']}: {exc}") from exc
                log(f"lipsync skip {item['id']}: {exc}")
        stretched.append(out)
        checkpoint.mark_done(
            item["id"],
            signature=checkpoint_signature,
            output=out,
            metadata={
                "target": item["target"],
                "checkpoint_contract": checkpoint_contract,
                "stretch_plan": item.get("stretch_plan"),
                "lipsync": next(
                    (entry for entry in reversed(lipsync_report) if entry.get("id") == item["id"]),
                    None,
                ),
            },
        )

    broll_edit_entries: list[dict[str, Any]] = []
    for index, item in enumerate(shot_audio):
        entries = item.get("dialogue_broll") or []
        if not entries:
            continue
        composite, entries_report = apply_dialogue_broll_visual(
            stretched[index],
            parent_id=str(item["id"]),
            parent_duration=float(item["target"]),
            entries=entries,
            work=work,
            width=width,
            height=height,
            fps=fps,
        )
        stretched[index] = composite
        broll_edit_entries.extend(entries_report)
    broll_edit_report = {
        "schema_version": 1,
        "audio_policy": "carry_parent_dialogue",
        "entries": [],
    }
    broll_edit_report_sha256: str | None = None
    if broll_edit_entries:
        broll_edit_report, _broll_report_path, broll_edit_report_sha256 = write_broll_edit_report(
            root, broll_edit_entries
        )

    # 3) Title / end cards
    # plate_cards=blank: keep pad duration for VO/SRT clock, no burned glyphs
    # (designed-post HyperFrames/Remotion draws the readable title once).
    plate_cards = str(getattr(args, "plate_cards", "blank") or "blank").strip().lower()
    if plate_cards not in {"text", "blank"}:
        raise RenderError("--plate-cards must be text|blank")
    title_text = args.title or spec.get("title") or manifest.get("title") or "AI Film"
    end_text = args.end_title or "— 完 —"
    title_mp4 = work / "title.mp4"
    end_mp4 = work / "end.mp4"
    title_dur = float(args.title_dur)
    end_dur = float(args.end_dur)
    title_draw = "" if plate_cards == "blank" else str(title_text)
    end_draw = "" if plate_cards == "blank" else str(end_text)
    if title_dur > 0.01:
        mkcard_video(
            title_draw,
            title_mp4,
            width=width,
            height=height,
            duration=title_dur,
            fps=fps,
            font_path=font_path,
        )
    if end_dur > 0.01:
        mkcard_video(
            end_draw,
            end_mp4,
            width=width,
            height=height,
            duration=end_dur,
            fps=fps,
            font_path=font_path,
        )

    # 4) Concat video parts: title + shots + end (per-join hard/soft/hold)
    try:
        transition_sec = normalize_transition_sec(
            getattr(args, "transition_sec", None)
            if getattr(args, "transition_sec", None) is not None
            else spec.get("transition_sec", DEFAULT_TRANSITION_SEC)
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    story_intents = spec.get("transition_intents")
    if story_intents is not None and not isinstance(story_intents, list):
        raise RenderError("film-spec transition_intents must be an array")
    default_intent = str(spec.get("transition_default") or "soft")
    try:
        full_join_intents = expand_story_join_intents(
            len(shot_audio),
            story_intents=list(story_intents) if story_intents is not None else None,
            default_intent=default_intent if transition_sec > 0 else "hard",
            edge_intent=default_intent if transition_sec > 0 else "hard",
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    parts: list[Path] = []
    if title_dur > 0.01:
        parts.append(title_mp4)
    parts.extend(stretched)
    if end_dur > 0.01:
        parts.append(end_mp4)
    silent = work / "video_silent.mp4"
    transition_style = str(spec.get("transition_style") or "fade").strip().lower() or "fade"
    story_styles = spec.get("transition_styles")
    if story_styles is not None and not isinstance(story_styles, list):
        raise RenderError("film-spec transition_styles must be an array")
    try:
        full_join_styles = expand_story_join_styles(
            len(shot_audio),
            story_styles=[str(x) for x in story_styles] if story_styles is not None else None,
            edge_style=transition_style,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    # Per-join transition duration from edit_strategy (voice-coupled rhythm)
    full_join_use_ts: list[float] | None = None
    raw_join_secs = spec.get("join_transition_secs")
    if isinstance(raw_join_secs, list) and len(raw_join_secs) == len(shot_audio) - 1:
        try:
            story_secs = [max(0.0, min(0.8, float(x))) for x in raw_join_secs]
            edge = float(transition_sec) if transition_sec > 0 else 0.05
            # title→s0, s0→s1…, sN→end  (len = n_shots + 1 when both pads present)
            n_parts = len(parts)
            n_joins = max(0, n_parts - 1)
            if n_joins == len(shot_audio) + 1:
                full_join_use_ts = [edge] + story_secs + [edge]
            elif n_joins == len(shot_audio):
                # missing one pad
                full_join_use_ts = [edge] + story_secs
            elif n_joins == len(shot_audio) - 1:
                full_join_use_ts = story_secs
            else:
                full_join_use_ts = None
            if full_join_use_ts is not None and len(full_join_use_ts) != n_joins:
                full_join_use_ts = None
        except (TypeError, ValueError):
            full_join_use_ts = None
    xfade_plan = concat_videos(
        parts,
        silent,
        transition_sec=transition_sec,
        fps=fps,
        join_intents=full_join_intents,
        transition_style=transition_style,
        join_styles=full_join_styles,
        join_use_ts=full_join_use_ts,
    )
    log(
        f"video concat method={xfade_plan.get('method')} transition_sec={transition_sec} "
        f"style={transition_style} styles={xfade_plan.get('join_styles')} "
        f"join_use_ts={full_join_use_ts} "
        f"enabled={xfade_plan.get('enabled')} joins={full_join_intents}"
    )

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
        """mute/duck on bgm bed, sfx_accent on sfx bed (upmixes mono to stereo)."""
        spotting: dict[str, Any]
        try:
            spotting = expand_sound_events(
                sound_plan,
                shot_starts=shot_start_map,
                total_duration=float(total_dur),
            )
        except SoundPlanError as exc:
            raise RenderError(str(exc)) from exc
        events = spotting.get("applied_events") or []

        if float_bed.ndim == 1:
            bgm_out = np.column_stack((float_bed, float_bed))
        elif float_bed.ndim == 2 and float_bed.shape[1] == 1:
            bgm_out = np.column_stack((float_bed[:, 0], float_bed[:, 0]))
        else:
            bgm_out = float_bed.copy()

        music_timeline = (
            (sound_plan or {}).get("music_timeline") if isinstance(sound_plan, dict) else None
        )
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
            spotting["sfx_overlay_count"] = sum(
                1 for e in events if e.get("type") == "sfx_accent" and e.get("overlay_applied")
            )
        else:
            spotting["sfx_overlay_count"] = 0
        spotting["bed_source"] = spotting.get("bed_source") or "unknown"
        return bgm_out, sfx_out, spotting

    # Anti-fatigue seed first (pool pick + procedural style share it)
    plan_mood = (sound_plan or {}).get("mood") if sound_plan else None
    if plan_mood:
        mood = str(plan_mood)
    seed_arg = getattr(args, "music_seed", None)
    policy_seed = None
    ap = spec.get("audio_policy") if isinstance(spec.get("audio_policy"), dict) else {}
    if ap.get("music_seed") is not None:
        try:
            policy_seed = int(ap["music_seed"])
        except (TypeError, ValueError):
            policy_seed = None
    if seed_arg is not None:
        music_seed = int(seed_arg)
    elif policy_seed is not None:
        music_seed = policy_seed
    else:
        title_s = str(spec.get("title") or root.name)
        # v3: style families; include recipe summary so different arcs reshuffle beds
        route = spec.get("_audio_routing") if isinstance(spec.get("_audio_routing"), dict) else {}
        counts = route.get("counts") if isinstance(route.get("counts"), dict) else {}
        count_key = ",".join(f"{k}{counts.get(k, 0)}" for k in sorted(counts))
        raw_seed = f"{title_s}|{mood}|{total_dur:.2f}|v3-multi-style|{count_key}"
        music_seed = int(hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:8], 16)

    # Phase 4: Plot-Adaptive Mood Timeline
    if isinstance(sound_plan, dict):
        sound_plan["mood_timeline"] = build_mood_timeline(
            shot_dicts, shot_starts=shot_start_map, shot_ends=shot_end_map, default_mood=mood
        )
        if build_music_timeline is not None:
            try:
                sound_plan["music_timeline"] = build_music_timeline(
                    shot_dicts,
                    shot_starts=shot_start_map,
                    shot_ends=shot_end_map,
                    default_mood=mood,
                )
                mix_spotting["music_cue_routing"] = summarize_music_timeline(
                    sound_plan["music_timeline"]
                )
                # Procedural generators consume the richer cue fields.
                sound_plan["mood_timeline"] = sound_plan["music_timeline"]
            except ValueError as exc:
                raise RenderError(f"invalid shot music_cue: {exc}") from exc

    # Phase H: local template pool. `timeline` is opt-in because it requires a
    # licensed mood-specific file for every cue; it never degrades to one loop.
    bed_source = str(ap.get("bed_source") or "auto").lower()
    template_mode = str(
        getattr(args, "music_template", None)
        or ("approved_library" if bed_source == "approved_library" else None)
        or (sound_plan or {}).get("music_template")
        or "auto"
    ).lower()
    template_timeline_samples: np.ndarray | None = None
    template_timeline_selections: list[dict[str, Any]] = []
    if template_mode in {"timeline", "approved_library"}:
        try:
            template_timeline_samples, template_timeline_selections = (
                render_music_template_timeline(
                    root=root,
                    work=work,
                    timeline=(sound_plan or {}).get("music_timeline") or [],
                    plan=sound_plan if isinstance(sound_plan, dict) else None,
                    music_license=getattr(args, "music_license", None),
                    seed=music_seed,
                    total_dur=total_dur,
                    approved_library=template_mode == "approved_library",
                    film_id=str(spec.get("id") or spec.get("title") or root.name),
                    series_id=str(spec.get("series_id") or ""),
                )
            )
        except (SoundPlanError, RenderError) as exc:
            raise RenderError(str(exc)) from exc
        music_resolved = None
    else:
        try:
            music_resolved = resolve_music_template(
                root,
                mood=mood,
                plan=sound_plan if isinstance(sound_plan, dict) else None,
                music_arg=getattr(args, "music", None),
                mode=getattr(args, "music_template", None),
                music_license=getattr(args, "music_license", None),
                seed=music_seed,
            )
        except SoundPlanError as exc:
            raise RenderError(str(exc)) from exc

    # Optional external AI music (ACE-Step / MusicGen…) when no local bed
    if music_resolved is None and template_timeline_samples is None:
        ext_music = _try_external_music_gen(
            work=work,
            duration=total_dur,
            mood=mood,
            seed=music_seed,
            title=str(spec.get("title") or root.name),
        )
        if ext_music is not None:
            music_resolved = ext_music

    mix_spotting["music_template"] = (
        {
            "source": music_resolved.get("source"),
            "path": music_resolved.get("relative") or music_resolved.get("path"),
            "mode": music_resolved.get("mode"),
            "pool_size": music_resolved.get("pool_size"),
            "pool_index": music_resolved.get("pool_index"),
        }
        if music_resolved
        else {"source": "procedural", "mode": getattr(args, "music_template", None) or "auto"}
    )
    if template_timeline_samples is not None:
        mix_spotting["music_template"] = {
            "source": (
                "approved_library" if template_mode == "approved_library" else "timeline_templates"
            ),
            "mode": template_mode,
            "cue_count": len(template_timeline_selections),
            "catalog_revision": (
                template_timeline_selections[0].get("catalog_revision")
                if template_timeline_selections
                else None
            ),
            "catalog_sha256": (
                template_timeline_selections[0].get("catalog_sha256")
                if template_timeline_selections
                else None
            ),
            "selections": [
                {
                    "shot_id": item["shot_id"],
                    "path": item["relative"],
                    "mood": item["mood"],
                    "motif_id": item["motif_id"],
                    "asset_id": item.get("asset_id"),
                    "sha256": item.get("sha256"),
                    "motif_family": item.get("motif_family"),
                    "parent_asset_id": item.get("parent_asset_id"),
                    "similarity_cluster": item.get("similarity_cluster"),
                    "selection_reason": item.get("selection_reason"),
                    "take_seed": item["take_seed"],
                    "license_note": item["license_note"],
                }
                for item in template_timeline_selections
            ],
        }
    mix_spotting["music_seed"] = music_seed

    if template_timeline_samples is not None:
        license_note = (
            "approved shared BGM library; see mix_report music_template.selections"
            if template_mode == "approved_library"
            else "timeline of licensed local BGM templates; see mix_report music_template.selections"
        )
        user_f, sfx_f, spotting_only = _apply_spotting_and_convert_to_stereo(
            template_timeline_samples
        )
        mix_spotting = {**mix_spotting, **spotting_only}
        mix_spotting["mood"] = "timeline"
        mix_spotting["bed_source"] = (
            "approved_library" if template_mode == "approved_library" else "timeline_templates"
        )
        mix_spotting["music_seed"] = music_seed
        mix_spotting["note"] = "mood-routed local BGM templates — mute/duck on bgm, sfx separated"
        if sound_plan and sound_plan.get("bed") is False:
            user_f = np.zeros_like(user_f)
            mix_spotting["bed_applied"] = False
        else:
            mix_spotting["bed_applied"] = True
        stereo = work / "bgm_stereo.wav"
        sfx_stereo_path = work / "sfx_stereo.wav"
        write_wav_stereo(stereo, (np.clip(user_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        write_wav_stereo(sfx_stereo_path, (np.clip(sfx_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        music_path = stereo
    elif music_resolved and Path(music_resolved["path"]).is_file():
        music_src = Path(music_resolved["path"]).expanduser().resolve()
        license_note = str(music_resolved.get("license_note") or "user-supplied file")
        mono_tmp = work / "bgm_user_mono.wav"
        # loop/trim to total mono for spotting, then stereo
        run(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(music_src),
                "-t",
                f"{total_dur:.3f}",
                "-ar",
                str(SR),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(mono_tmp),
            ]
        )
        # load mono int16
        with wave.open(str(mono_tmp), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            user_i16 = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32767.0
        user_f, sfx_f, spotting_only = _apply_spotting_and_convert_to_stereo(user_i16)
        # keep multi-track voice metadata (not wiped by bed spotting)
        mix_spotting = {**mix_spotting, **spotting_only}
        mix_spotting["mood"] = (sound_plan or {}).get("mood", mood) if sound_plan else mood
        mix_spotting["bed_source"] = str(music_resolved.get("source") or "user_music_file")
        mix_spotting["music_seed"] = music_seed
        mix_spotting["note"] = "user/external music — mute/duck on bgm, sfx separated"
        if sound_plan and sound_plan.get("bed") is False:
            user_f = np.zeros_like(user_f)
            mix_spotting["bed_applied"] = False
        else:
            mix_spotting["bed_applied"] = True
        stereo = work / "bgm_stereo.wav"
        sfx_stereo_path = work / "sfx_stereo.wav"
        write_wav_stereo(stereo, (np.clip(user_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        write_wav_stereo(sfx_stereo_path, (np.clip(sfx_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        music_path = stereo
    else:
        license_note = "original generative numpy score (ai-film-grok procedural v3 multi-style, no third-party samples)"
        # IMPORTANT: generate BGM at fixed healthy amp — do NOT multiply by music_volume here
        # (music_volume is applied once in the dual-track mix below)
        gen_amp = float(getattr(args, "bgm_gen_amp", None) or DEFAULT_BGM_GEN_AMP)
        bg_hint = 1.0
        try:
            bg_hint = float(
                (sound_plan or {}).get("bed_gain_hint")
                or (spec.get("_audio_routing") or {}).get("mean_bed_gain")
                or 1.0
            )
        except (TypeError, ValueError):
            bg_hint = 1.0
        s_starts = []
        acc = title_dur
        for item in shot_audio:
            s_starts.append(acc)
            acc += float(item.get("target") or 6.0)

        samples = procedural_music(
            total_dur,
            emo=1.1,
            curve="swell",
            amp=gen_amp,
            mood=mood,
            seed=music_seed,
            shot_starts=s_starts,
            events=(sound_plan or {}).get("events"),
            mood_timeline=(sound_plan or {}).get("mood_timeline"),
        )
        float_bed = samples.astype(np.float64) / 32767.0
        float_bed, sfx_f, spotting_only = _apply_spotting_and_convert_to_stereo(float_bed)
        mix_spotting = {**mix_spotting, **spotting_only}
        mix_spotting["bed_source"] = "procedural"
        mix_spotting["music_seed"] = music_seed
        mix_spotting["bed_gain_hint"] = bg_hint
        try:
            from make_sfx_bed import last_rnb_style, pick_rnb_style  # type: ignore

            mix_spotting["procedural_style"] = last_rnb_style() or pick_rnb_style(music_seed)
        except Exception:
            mix_spotting["procedural_style"] = "unknown"
        log(
            f"BGM procedural seed={music_seed} style={mix_spotting.get('procedural_style')} "
            f"(change --music-seed for another take/style)"
        )
        if sound_plan and sound_plan.get("bed") is False:
            float_bed = np.zeros_like(float_bed)
            mix_spotting["bed_applied"] = False
        else:
            mix_spotting["bed_applied"] = True
        stereo = work / "bgm_stereo.wav"
        sfx_stereo_path = work / "sfx_stereo.wav"
        write_wav_stereo(stereo, (np.clip(float_bed, -1.0, 1.0) * 32767.0).astype(np.int16))
        write_wav_stereo(sfx_stereo_path, (np.clip(sfx_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        music_path = stereo

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
    try:
        run(mix_cmd)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as mix_exc:
        prior_sc = mix_spotting.get("sidechain_applied")
        if not prior_sc:
            raise RenderError(
                f"audio mix failed (no sidechain to fall back from): {mix_exc}"
            ) from mix_exc
        log(
            f"sidechain mix failed ({type(mix_exc).__name__}) → simple amix PARTIAL "
            f"(was {prior_sc!r})"
        )
        # Remove partial output if any
        with contextlib.suppress(OSError):
            if mixed.is_file():
                mixed.unlink()
        color_in = "[6:a]" if use_color else ""
        # Input order: 0 narr, 1 music, 2 native, 3 sfx, 4 scene, 5 ambience, [6 color]
        n_in = 6 + (1 if use_color else 0)
        simple_fc = (
            f"[0:a][1:a][2:a][3:a][4:a][5:a]{color_in}"
            f"amix=inputs={n_in}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        simple_cmd = [
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
            simple_cmd.extend(["-i", str(color_track)])
        simple_cmd.extend(
            [
                "-filter_complex",
                simple_fc,
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
        try:
            run(simple_cmd)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as amix_exc:
            raise RenderError(
                f"audio mix failed after sidechain→amix fallback: {amix_exc}"
            ) from amix_exc
        mix_spotting["sidechain_applied"] = False
        mix_spotting["sidechain_fallback"] = {
            "from": prior_sc,
            "to": "amix_simple",
            "partial": True,
            "error": str(mix_exc)[:300],
            "error_type": type(mix_exc).__name__,
        }
        mix_spotting["delivery_partial"] = True
        mix_spotting["partial_reason"] = "sidechain_mix_failed_amix_fallback"
        # Persist PARTIAL receipt for closeout / agents (not silent quality pass)
        try:
            partial_path = write_final_mix_partial_receipt(
                root,
                prior_sc=str(prior_sc),
                error=str(mix_exc),
                mixed=mixed,
            )
            mix_spotting["partial_receipt"] = str(partial_path)
        except Exception as rec_exc:  # noqa: BLE001
            mix_spotting["partial_receipt_error"] = str(rec_exc)[:160]

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

    # 8) Subtitle cues — char-weighted, early; same xfade clock as picture/VO/native
    # P0 · 2026-07-24: default 0 — positive lead caused SRT overlap hard-fail on dense ZH units
    sub_lead = float(getattr(args, "sub_lead", 0.0) or 0.0)
    sub_min = float(getattr(args, "sub_min_unit", 0.48) or 0.48)
    sub_max = float(getattr(args, "sub_max_unit", 1.75) or 1.75)
    cues, film_tl = build_subtitle_cues_for_shots(
        shot_audio,
        title_duration=title_dur,
        end_duration=end_dur,
        transition_sec=active_transition,
        sub_lead=sub_lead,
        sub_min=sub_min,
        sub_max=sub_max,
        story_join_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent if active_transition > 0 else "hard",
    )
    event_caption_bindings: list[dict[str, Any]] | None = None
    if use_event_tts and formal_timeline is not None:
        event_caption_bindings = timeline_caption_bindings(formal_timeline)
        cues = [
            {
                "start": row["start_sec"],
                "end": row["end_sec"],
                "text": row["caption_text"],
                "audio_event_id": row["audio_event_id"],
            }
            for row in event_caption_bindings
        ]
        write_json(audio_dir / "event-subtitle-bindings.json", event_caption_bindings)

    try:
        srt_path = safe_output_path(
            out_dir, "final.srt", suffixes={".srt"}, field="subtitle sidecar"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    write_srt(srt_path, cues, preserve_overlaps=use_event_tts)
    # Wave D · if film root path has spaces, also mirror SRT to /tmp for any
    # libass/subtitles= consumers (PIL burn already uses PNG overlays, no force_style).
    srt_stable = stable_path_for_ffmpeg_filter(srt_path, suffix=".srt", prefix="aifilm-srt")
    if srt_stable != srt_path:
        log(f"SRT mirrored to space-free path for ffmpeg filters: {srt_stable}")

    # Burn subs with PIL overlays (no drawtext dependency).
    # --subs off keeps SRT only (for HyperFrames designed captions underlay path).
    subs_mode = resolve_subtitle_mode(args)
    video_subbed = work / "video_subbed.mp4"
    if subs_mode == "off" or not cues:
        shutil.copy2(silent, video_subbed)
    else:
        overlay_inputs: list[str] = ["-i", str(silent)]
        filter_parts: list[str] = []
        last = "[0:v]"
        oidx = 1
        for i, cue in enumerate(cues):
            png = overlays_dir / f"sub_{i:03d}.png"
            shot_index = cue.get("shot_index", 0)
            shot = shot_dicts[shot_index] if shot_dicts and shot_index < len(shot_dicts) else {}
            safe_area = (shot.get("dsl") or {}).get("safe_area") or {}

            # Subtitles default to bottom, but we dodge to top if subtitle_clear is explicitly false
            dodge = safe_area.get("subtitle_clear") is False
            italic = cue.get("is_monologue", False)

            sub_png(
                cue["text"],
                png,
                width=width,
                height=height,
                font_path=font_path,
                dodge=dodge,
                italic=italic,
            )
            overlay_inputs += ["-i", str(png)]
            out_label = f"[o{i}]"
            filter_parts.append(
                f"{last}[{oidx}:v]overlay=0:0:enable='between(t,{cue['start']:.3f},{cue['end']:.3f})'{out_label}"
            )
            last = out_label
            oidx += 1
        if filter_parts:
            run(
                [
                    "ffmpeg",
                    "-y",
                    *overlay_inputs,
                    "-filter_complex",
                    ";".join(filter_parts),
                    "-map",
                    last,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    str(video_subbed),
                ]
            )
        else:
            shutil.copy2(silent, video_subbed)

    # 9) Mux final
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_subbed),
            "-i",
            str(mixed),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(final_path),
        ]
    )

    # Verify streams
    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(final_path),
        ]
    )
    streams = json.loads(probe.stdout).get("streams") or []
    has_v = any(s.get("codec_type") == "video" for s in streams)
    has_a = any(s.get("codec_type") == "audio" for s in streams)
    if not has_v or not has_a:
        raise RenderError("Final MP4 missing video or audio stream")
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if bool(spec.get("audio_timeline_v1", False)) and (
        not audio_stream
        or str(audio_stream.get("sample_rate")) != "48000"
        or int(audio_stream.get("channels") or 0) != 2
    ):
        raise RenderError("audio_timeline_v1 final must be 48kHz stereo")

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
            "mode": lipsync_mode,
            "probe": lipsync_probe() if lipsync_probe else None,
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

    # Update manifest gates
    manifest.setdefault("outputs", {})["final_film"] = {
        "path": str(final_path.name),  # store relative name when under out/
        "sha256": report["output_sha256"],
        "duration_sec": report["duration_sec"],
        "report": str(report_path.name),
        "assembled_at": utc_now(),
        "technical_qa": technical_qa,
    }
    # Technical success is not human/agent end-to-end approval.
    manifest.setdefault("gates", {})["final_complete"] = False
    manifest["updated_at"] = utc_now()
    write_json(root / "manifest.json", manifest)

    return {
        "ok": True,
        "output": str(final_path),
        "duration_sec": report["duration_sec"],
        "srt": str(srt_path),
        "report": str(report_path),
        "cue_count": len(cues),
        "music_license": license_note,
        "lipsync_shots": lipsync_report,
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
        choices=["auto", "off", "require", "latentsync", "external", "wav2lip"],
        help="Lip-sync OFF by default; RTX node uses LatentSync for approved close-up repair.",
    )
    p.add_argument(
        "--allow-loop-risk",
        action="store_true",
        help="Allow final even when VO would stream_loop short plates (discouraged)",
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
        result = render_final(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RenderError, subprocess.CalledProcessError, ValueError) as exc:
        err = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            err = (exc.stderr or exc.stdout or str(exc))[:2000]
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
