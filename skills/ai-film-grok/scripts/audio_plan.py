#!/usr/bin/env python3
"""Dry-run audio plan for a film root (TTS / BGM / lipsync) — no render."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any  # noqa: F401 — used in shots_dry

from util import read_json


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def build_audio_plan(
    root: Path,
    *,
    compile_timeline: bool = False,
    write_timeline: bool = False,
    write_voice_cast: bool = False,
    write_tts_manifest: bool = False,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    scripts = skill_dir() / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    spec = read_json(root / "film-spec.json") or {}
    timeline: dict[str, Any] | None = None
    timeline_error: str | None = None
    voice_cast: dict[str, Any] | None = None
    tts_manifest: dict[str, Any] | None = None
    try:
        from audio_timeline import build_mix_execution_plan, caption_bindings, validate_timeline
        from audio_timeline import compile_timeline as compile_audio_timeline
        from audio_timeline import write_timeline as persist_timeline

        timeline = compile_audio_timeline(spec)
        validate_timeline(timeline)
        if write_timeline:
            path = persist_timeline(root, timeline)
            timeline["path"] = str(path)
        timeline["caption_bindings"] = caption_bindings(timeline)
        timeline["mix_execution"] = build_mix_execution_plan(
            timeline, sample_rate=48000 if spec.get("audio_timeline_v1") else 44100
        )
        if write_voice_cast:
            import json

            from voice_cast_profiles import VOCAL_LANGUAGE, assign_profiles

            old_path = root / "audio" / "voice-cast.json"
            old = read_json(old_path) if old_path.is_file() else {}
            old_profiles = old.get("profiles") if isinstance(old, dict) else {}
            speakers: dict[str, dict[str, str]] = {}
            for event in timeline["events"]:
                if event.get("type") in VOCAL_LANGUAGE and event.get("speaker"):
                    sid = str(event["speaker"])
                    speakers.setdefault(
                        sid,
                        {"speaker_id": sid, "language": VOCAL_LANGUAGE[str(event["type"])]},
                    )
            voice_cast = {
                "schema_version": 1,
                "kind": "voice-cast",
                "profiles": assign_profiles(list(speakers.values()), old_profiles),
            }
            old_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_text(
                json.dumps(voice_cast, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        if write_tts_manifest:
            import json

            from audio_tts_manifest import build_tts_manifest
            from voice_cast_profiles import VOCAL_LANGUAGE, assign_profiles

            if voice_cast is None:
                speakers = {
                    str(event["speaker"]): {
                        "speaker_id": str(event["speaker"]),
                        "language": VOCAL_LANGUAGE[str(event["type"])],
                    }
                    for event in timeline["events"]
                    if event.get("type") in VOCAL_LANGUAGE and event.get("speaker")
                }
                voice_cast = {"profiles": assign_profiles(list(speakers.values()))}
            tts_manifest = build_tts_manifest(timeline, voice_cast)
            manifest_path = root / "audio" / "tts-manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(tts_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    except Exception as exc:  # noqa: BLE001 - report compiler blockers in dry-run
        timeline_error = str(exc)
    tts_backend = str(spec.get("tts_backend") or "edge").lower()
    vo_voice = spec.get("vo_voice")
    mood = "rnb"
    sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    if sp.get("mood"):
        mood = str(sp.get("mood"))
    elif spec.get("music_mood"):
        mood = str(spec.get("music_mood"))

    tts_info: dict[str, Any] = {}
    try:
        from tts_backend import probe

        tts_info = probe()
    except Exception as exc:  # noqa: BLE001
        tts_info = {"ok": False, "error": str(exc)}

    music_resolved = None
    music_error = None
    try:
        from sound_plan import resolve_music_template

        music_resolved = resolve_music_template(
            root,
            mood=mood,
            plan=sp or None,
            mode=sp.get("music_template") if sp else "auto",
        )
    except Exception as exc:  # noqa: BLE001
        music_error = str(exc)[:300]

    lipsync_info: dict[str, Any] = {}
    try:
        from lipsync_backend import probe as lipsync_probe

        lipsync_info = lipsync_probe()
    except Exception as exc:  # noqa: BLE001
        lipsync_info = {"ok": False, "error": str(exc)}

    lipsync_shots: list[str] = []
    for shot in spec.get("shots") or []:
        if isinstance(shot, dict) and shot.get("lipsync") is True:
            sid = str(shot.get("id") or shot.get("shot_id") or "")
            if sid:
                lipsync_shots.append(sid)

    vo_mode = str(spec.get("vo_mode") or "storyteller")
    recommendations: list[str] = []
    if tts_backend in {"auto", "edge"} and tts_info.get("backends", {}).get("edge"):
        recommendations.append("TTS: edge ready (default for Chinese storyteller)")
    if not tts_info.get("voicebox_ok"):
        recommendations.append("TTS quality: start Voicebox + VOICEBOX_PROFILE")
    if music_resolved is None and not music_error:
        recommendations.append("BGM: no template — final will use procedural bed")
    elif music_resolved:
        recommendations.append(
            f"BGM: {music_resolved.get('source')} → {music_resolved.get('path') or music_resolved.get('relative')}"
        )
    if vo_mode == "storyteller" and lipsync_shots:
        recommendations.append(
            "lipsync: storyteller usually forces off; clear shot.lipsync or use character mode"
        )
    if lipsync_shots and not (lipsync_info.get("ready") or []):
        recommendations.append(
            "lipsync targets set but no locked backend — lipsync-canary after backend-lock"
        )

    # Scene-adaptive recipes (from write-spec) or dry-run resolve
    routing = spec.get("_audio_routing") if isinstance(spec.get("_audio_routing"), dict) else None
    policy = spec.get("audio_policy") if isinstance(spec.get("audio_policy"), dict) else None
    if routing is None:
        try:
            from audio_recipe import apply_audio_recipes_to_spec, probe_caps_for_root

            # work on a shallow copy of shots for dry-run display
            shots_dry: list[Any] = []
            for scene in spec.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict):
                        shots_dry.append(dict(sh))
            if not shots_dry and isinstance(spec.get("shots"), list):
                shots_dry = [dict(s) for s in spec["shots"] if isinstance(s, dict)]
            caps = probe_caps_for_root(root)
            routing = apply_audio_recipes_to_spec(
                spec,
                shots_dry,
                lipsync_ready=bool(caps.get("lipsync_ready")),
                music_library=bool(caps.get("music_library")),
                sung_provider_ready=bool(caps.get("sung_provider_ready")),
            )
            policy = (
                spec.get("audio_policy") if isinstance(spec.get("audio_policy"), dict) else policy
            )
        except Exception as exc:  # noqa: BLE001
            routing = {"ok": False, "error": str(exc)[:200]}

    if isinstance(routing, dict) and routing.get("counts"):
        c = routing["counts"]
        recommendations.append("audio_recipe: " + ", ".join(f"{k}={v}" for k, v in c.items() if v))
    if isinstance(policy, dict) and policy.get("mode") == "musical_hybrid":
        if not policy.get("allow_sung"):
            recommendations.append("musical_hybrid but allow_sung=false — no sung_beat")
        else:
            recommendations.append(
                "musical_hybrid: up to "
                f"{policy.get('max_sung_shots', 1)} sung_beat near climax (needs provider)"
            )

    return {
        "ok": True,
        "kind": "ai-film-audio-plan",
        "root": str(root),
        "vo_mode": vo_mode,
        "audio_policy": policy,
        "audio_routing": routing,
        "tts": {
            "film_spec_backend": tts_backend,
            "vo_voice": vo_voice,
            "probe_active": tts_info.get("active"),
            "edge": bool((tts_info.get("backends") or {}).get("edge")),
            "voicebox": bool(tts_info.get("voicebox_ok")),
            "fallback_enabled": bool(tts_info.get("voicebox_fallback")),
        },
        "music": {
            "mood": mood,
            "resolved": music_resolved,
            "error": music_error,
            "will_use": (
                "user_or_template" if music_resolved else ("error" if music_error else "procedural")
            ),
            "bed_source_policy": (policy or {}).get("bed_source") if policy else "auto",
            "mean_bed_gain": (routing or {}).get("mean_bed_gain") if routing else None,
        },
        "sfx": {
            "auto_sfx": sp.get("auto_sfx", True) if sp else True,
        },
        "audio_timeline": {
            "enabled": bool(spec.get("audio_timeline_v1", False)),
            "compiled": timeline is not None,
            "timeline": timeline if compile_timeline else None,
            "event_count": len((timeline or {}).get("events") or []),
            "caption_binding_count": len((timeline or {}).get("caption_bindings") or []),
            "mix_lane_count": len(((timeline or {}).get("mix_execution") or {}).get("lanes") or []),
            "error": timeline_error,
        },
        "voice_cast": voice_cast,
        "tts_manifest": tts_manifest,
        "lipsync": {
            "env_backend": lipsync_info.get("env_backend"),
            "ready": lipsync_info.get("ready") or [],
            "target_shots": lipsync_shots,
            "storyteller_default_off": vo_mode == "storyteller",
        },
        "recommendations": recommendations,
        "ref": "references/audio-recipe.md",
    }
