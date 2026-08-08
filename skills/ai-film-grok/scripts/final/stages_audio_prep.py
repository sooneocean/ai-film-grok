"""Audio prep before BGM bed: spotting maps, timeline, scene stems (W1.8).

Structure-only peel of render_final stage 6 prefix (before music bed leaf).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from audio_cues import compile_audio_timeline
from audio_timeline import AudioTimelineError, build_mix_execution_plan, rebase_to_rendered_shots
from audio_timeline import compile_timeline as compile_audio_timeline_v1
from audio_timeline import timeline_hash as audio_timeline_hash
from edit_policy import film_segment_timeline
from event_voice_stem import EventVoiceStemError, render_event_voice_stem
from final.caption_text import flatten_shots
from final.errors import RenderError
from final.io import read_json
from final.tts_tracks import build_vocal_color_track
from logger import log
from narrative_timeline import NarrativeTimelineError, validate_sfx_scene_bindings
from runtime_policy import sha256
from scene_sound_stems import SceneSoundError, render_scene_sound_stem
from security_policy import SecurityPolicyError, safe_output_path
from sound_plan import inject_auto_sfx_if_empty
from util import write_json


def prepare_audio_mix_context(
    *,
    root: Path,
    work: Path,
    audio_dir: Path,
    args: Any,
    spec: dict[str, Any],
    shots: list[dict[str, Any]],
    shot_audio: list[dict[str, Any]],
    mood: str,
    vo_gain: float,
    film_vocal_color_gain: float,
    native_audio_volume: float,
    voice_policy: dict[str, Any],
    scene_sound_report: dict[str, Any],
    title_dur: float,
    end_dur: float,
    active_transition: float,
    story_intents: list[Any] | None,
    default_intent: str,
    total_dur: float,
    voice_cat: Path,
    silence_wav: Callable[[Path, float], None],
    sound_cues_to_sfx_kinds: Callable[..., Any] | None,
) -> dict[str, Any]:
    """Build mix_spotting, formal timeline, scene/ambience stems, sound_plan, color track."""
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


    return {
        "music_path": music_path,
        "mix_spotting": mix_spotting,
        "shot_start_map": shot_start_map,
        "shot_end_map": shot_end_map,
        "shot_duration_map": shot_duration_map,
        "audio_timeline_path": audio_timeline_path,
        "formal_timeline": formal_timeline,
        "formal_silence_windows": formal_silence_windows,
        "event_voice_stem": event_voice_stem,
        "use_event_tts": use_event_tts,
        "voice_cat": voice_cat,
        "scene_sound_path": scene_sound_path,
        "ambience_path": ambience_path,
        "scene_sound": scene_sound,
        "ambience_volume": ambience_volume,
        "sound_plan": sound_plan,
        "shot_dicts": shot_dicts,
        "color_track": color_track,
        "apply_spotting": _apply_spotting_and_convert_to_stereo,
    }
