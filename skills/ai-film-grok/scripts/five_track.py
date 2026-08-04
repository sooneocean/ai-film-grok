#!/usr/bin/env python3
"""5-Track cinema mix policy (Wave δ · 2026-08-04).

Maps product tracks to the real render_final stems:

  DX  → voice / VO concat (dialogue)
  FX  → sfx_stereo.wav + sex_sfx / sfx_accent events
  BG  → ambience_stereo.wav + scene_sound bed
  MX  → bgm_stereo.wav (sidechain under DX)
  SUB → optional LFE pulse (plan-only until dedicated stem)

Target loudness: integrated **-16 LUFS ±1.5** (lufs_min=-17.5, lufs_max=-14.5).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

# Product loudness (5track-audio-master)
LUFS_TARGET = -16.0
LUFS_TOLERANCE = 1.5
LUFS_MIN_DEFAULT = LUFS_TARGET - LUFS_TOLERANCE  # -17.5
LUFS_MAX_DEFAULT = LUFS_TARGET + LUFS_TOLERANCE  # -14.5

TRACK_IDS = ("dx", "fx", "bg", "mx", "sub")

# render_final artifact names under audio/
STEM_FILES = {
    "dx": ("voice_concat.wav", "vo_concat.wav", "dialogue.wav"),
    "fx": ("sfx_stereo.wav", "sfx.wav"),
    "bg": ("ambience_stereo.wav", "scene_sound_stereo.wav"),
    "mx": ("bgm_stereo.wav", "music.wav", "bgm.wav"),
    "sub": ("lfe_stereo.wav", "sub_stereo.wav"),  # optional
    "mixed": ("mixed.wav",),
}

MEAT_PHASES = frozenset({"act", "climax", "foreplay"})


class FiveTrackError(ValueError):
    pass


def policy_skip_enabled() -> bool:
    return os.environ.get("AIFILM_SKIP_FIVE_TRACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def five_track_enabled(spec: dict[str, Any] | None) -> bool:
    """When to auto-apply 5-track defaults + LUFS band."""
    if policy_skip_enabled():
        return False
    spec = spec if isinstance(spec, dict) else {}
    if spec.get("five_track") is False or spec.get("five_track_enabled") is False:
        return False
    if spec.get("five_track") is True or spec.get("five_track_enabled") is True:
        return True
    if isinstance(spec.get("five_track"), dict) and spec["five_track"].get("enabled") is False:
        return False
    vo = str(spec.get("vo_mode") or "").strip().lower()
    if vo == "dialogue_drama":
        return True
    heat = str(spec.get("heat_scale") or "").strip().lower()
    if heat in {"max", "hot", "extreme"}:
        return True
    # production-book quality may be mirrored on film-spec.quality_target
    qt = str(spec.get("quality_target") or "").strip().lower()
    if qt == "premium_vertical":
        return True
    genre = str(spec.get("genre") or "").strip().lower()
    if genre in {"adult", "dialogue", "dialogue_drama"}:
        return True
    return bool(spec.get("lufs_strict") or spec.get("audio_tracks_strict"))


def lufs_band_for_spec(spec: dict[str, Any] | None) -> dict[str, float | bool]:
    """Resolve integrated LUFS gate band."""
    spec = spec if isinstance(spec, dict) else {}
    enabled = five_track_enabled(spec)
    strict = bool(spec.get("lufs_strict"))
    if enabled and "lufs_strict" not in spec:
        strict = True  # default hard for cinema path
    lo = float(spec.get("lufs_min") if spec.get("lufs_min") is not None else LUFS_MIN_DEFAULT)
    hi = float(spec.get("lufs_max") if spec.get("lufs_max") is not None else LUFS_MAX_DEFAULT)
    if enabled and spec.get("lufs_min") is None and spec.get("lufs_max") is None:
        lo, hi = LUFS_MIN_DEFAULT, LUFS_MAX_DEFAULT
    return {
        "enabled": enabled,
        "strict": strict,
        "target": LUFS_TARGET,
        "tolerance": LUFS_TOLERANCE,
        "lufs_min": lo,
        "lufs_max": hi,
    }


def default_audio_tracks_block(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Canonical audio_tracks object for sound_plan / film-spec."""
    mood = "rnb"
    if isinstance(spec, dict):
        sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
        mood = str(sp.get("mood") or spec.get("music_mood") or "rnb")
    return {
        "dx": {
            "role": "dialogue",
            "source": "tts_edge_or_native_h3",
            "license": "generated",
            "note": "Chinese dialogue / VO; sidechain key for MX",
        },
        "fx": {
            "role": "foley_sfx",
            "source": "procedural_sfx_bed+sex_sfx_events",
            "license": "generated",
            "note": "spot Foley; meat shots require sex_sfx accents",
        },
        "bg": {
            "role": "ambience",
            "source": "scene_sound+ambience_stereo",
            "license": "generated",
            "note": "continuous room tone; no long silent holes",
        },
        "mx": {
            "role": "music",
            "source": f"procedural_or_library_{mood}",
            "license": "generated_or_library",
            "mood": mood,
            "sidechain_under": "dx",
            "note": "BGM ducked under DX via sidechaincompress",
        },
        "sub": {
            "role": "lfe",
            "source": "optional_pulse",
            "license": "generated",
            "required": False,
            "note": "LFE pulses at dramatic peaks only (optional MVP)",
        },
        # legacy aliases used by validate_audio_tracks_contract
        "dialogue": {"source": "tts", "license": "generated", "alias_of": "dx"},
        "sfx": {"source": "procedural", "license": "generated", "alias_of": "fx"},
        "music": {"source": f"bgm_{mood}", "license": "generated_or_library", "alias_of": "mx"},
        "ambience": {"source": "room_tone", "license": "generated", "alias_of": "bg"},
    }


def ensure_five_track_defaults(spec: dict[str, Any]) -> dict[str, Any]:
    """Mutate film-spec: audio_tracks + LUFS defaults when cinema path enabled."""
    if not isinstance(spec, dict):
        return {"ok": False, "enabled": False, "applied": []}
    if not five_track_enabled(spec):
        return {"ok": True, "enabled": False, "applied": [], "skipped": True}

    applied: list[str] = []
    sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    if not isinstance(spec.get("sound_plan"), dict):
        sp = {}
        spec["sound_plan"] = sp

    tracks = sp.get("audio_tracks") if isinstance(sp.get("audio_tracks"), dict) else None
    if tracks is None and isinstance(spec.get("audio_tracks"), dict):
        tracks = spec["audio_tracks"]
    if not isinstance(tracks, dict) or not tracks:
        tracks = default_audio_tracks_block(spec)
        sp["audio_tracks"] = tracks
        spec["audio_tracks"] = tracks
        applied.append("audio_tracks_default")
    else:
        # merge missing keys only
        defaults = default_audio_tracks_block(spec)
        for key in ("dx", "fx", "bg", "mx", "sub", "dialogue", "sfx", "music", "ambience"):
            if key not in tracks and key in defaults:
                tracks[key] = defaults[key]
                applied.append(f"audio_tracks.{key}")
        sp["audio_tracks"] = tracks
        spec["audio_tracks"] = tracks

    ft = sp.get("five_track") if isinstance(sp.get("five_track"), dict) else {}
    ft = {
        **ft,
        "enabled": True,
        "schema": "five_track_v1",
        "tracks": list(TRACK_IDS),
        "lufs_target": LUFS_TARGET,
        "mapping": {
            "dx": "voice_concat",
            "fx": "sfx_stereo",
            "bg": "ambience+scene_sound",
            "mx": "bgm_sidechain",
            "sub": "optional_lfe",
        },
    }
    sp["five_track"] = ft
    spec["sound_plan"] = sp
    if "five_track" not in spec:
        spec["five_track"] = {"enabled": True, "schema": "five_track_v1"}
        applied.append("five_track.enabled")

    band = lufs_band_for_spec(spec)
    if spec.get("lufs_min") is None:
        spec["lufs_min"] = band["lufs_min"]
        applied.append(f"lufs_min={band['lufs_min']}")
    if spec.get("lufs_max") is None:
        spec["lufs_max"] = band["lufs_max"]
        applied.append(f"lufs_max={band['lufs_max']}")
    if "lufs_strict" not in spec:
        spec["lufs_strict"] = bool(band["strict"])
        applied.append(f"lufs_strict={spec['lufs_strict']}")

    report = {
        "ok": True,
        "enabled": True,
        "applied": applied,
        "lufs": band,
        "tracks": list(TRACK_IDS),
        "at": utc_now(),
        "note": "5-Track MVP: DX+FX+BG+MX required stems; SUB optional",
    }
    sp["_five_track"] = report
    return report


def _stem_present(audio_dir: Path, keys: tuple[str, ...]) -> Path | None:
    for name in keys:
        p = audio_dir / name
        if p.is_file() and p.stat().st_size > 44:
            return p
    return None


def _meat_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            ph = str(shot.get("heat_phase") or "").strip().lower()
            if ph in MEAT_PHASES:
                out.append(shot)
    return out


def _sex_sfx_coverage(spec: dict[str, Any]) -> dict[str, Any]:
    meat = _meat_shots(spec)
    if not meat:
        return {"ok": True, "required": 0, "covered": 0, "missing": []}
    sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    events = sp.get("events") if isinstance(sp.get("events"), list) else []
    covered = {
        str(e.get("shot_id"))
        for e in events
        if isinstance(e, dict) and e.get("sex_sfx") is True and str(e.get("shot_id") or "").strip()
    }
    missing = [str(s.get("id")) for s in meat if str(s.get("id")) not in covered]
    return {
        "ok": not missing,
        "required": len(meat),
        "covered": len(meat) - len(missing),
        "missing": missing,
    }


def plan_five_track(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Inventory stems + sex_sfx + loudness plan for a film root."""
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    if not isinstance(spec, dict):
        spec = {}
    ensure_rep = ensure_five_track_defaults(spec)
    # persist defaults back if applied
    if write and ensure_rep.get("applied"):
        write_json(base / "film-spec.json", spec)

    audio_dir = base / "audio"
    stems: dict[str, Any] = {}
    for tid in TRACK_IDS:
        path = _stem_present(audio_dir, STEM_FILES.get(tid, ()))
        stems[tid] = {
            "present": path is not None,
            "path": str(path) if path else None,
            "required": tid != "sub",
        }
    mixed = _stem_present(audio_dir, STEM_FILES["mixed"])
    mix_report = (
        read_json(audio_dir / "mix_report.json")
        if (audio_dir / "mix_report.json").is_file()
        else {}
    )
    loudness = {}
    if isinstance(mix_report, dict):
        loudness = mix_report.get("loudness") or mix_report.get("loudness_after") or {}
        if not isinstance(loudness, dict):
            loudness = {}
        arts = mix_report.get("artifacts") if isinstance(mix_report.get("artifacts"), dict) else {}
    else:
        arts = {}

    sex = _sex_sfx_coverage(spec)
    band = lufs_band_for_spec(spec)
    issues: list[dict[str, Any]] = []
    for tid, info in stems.items():
        if info.get("required") and not info.get("present") and mixed:
            # after final: missing named stem is warning if mixed exists
            issues.append(
                {
                    "code": f"STEM_MISSING_{tid.upper()}",
                    "severity": "warning",
                    "message": f"5-track {tid} stem file not found under audio/",
                }
            )
    if not sex.get("ok"):
        issues.append(
            {
                "code": "FIVE_TRACK_FX_SEX_SFX_MISSING",
                "severity": "error" if five_track_enabled(spec) else "warning",
                "message": (f"meat shots missing sex_sfx: {sex.get('missing')}"),
            }
        )
    if mixed and not arts:
        issues.append(
            {
                "code": "MIX_ARTIFACTS_MISSING",
                "severity": "warning",
                "message": "mix_report.artifacts missing (bgm/sfx/mixed hashes)",
            }
        )
    integrated = loudness.get("integrated") or loudness.get("integrated_lufs")
    if integrated is not None and band.get("enabled"):
        val = float(integrated)
        if val < float(band["lufs_min"]) or val > float(band["lufs_max"]):
            issues.append(
                {
                    "code": "LUFS_OUT_OF_RANGE",
                    "severity": "error" if band.get("strict") else "warning",
                    "message": (
                        f"integrated={val:.1f} LUFS outside "
                        f"[{band['lufs_min']}, {band['lufs_max']}] (target {LUFS_TARGET})"
                    ),
                }
            )

    errors = [i for i in issues if i.get("severity") == "error"]
    report = {
        "schema_version": 1,
        "kind": "five-track-plan",
        "at": utc_now(),
        "root": str(base),
        "ok": not errors,
        "enabled": five_track_enabled(spec),
        "ensure": ensure_rep,
        "lufs": band,
        "stems": stems,
        "mixed_present": mixed is not None,
        "mixed_path": str(mixed) if mixed else None,
        "sex_sfx": sex,
        "loudness": loudness,
        "mix_artifacts": bool(arts),
        "issues": issues,
        "codes": [str(i.get("code")) for i in issues],
        "next_cmd": (
            None
            if not errors
            else (
                'aifilm final --root "<film>" --music-mood rnb  # rebuild mix; '
                "or inject sex_sfx via write-spec / sound_plan"
            )
        ),
        "note": (
            "MVP maps DX=voice FX=sfx BG=ambience MX=bgm sidechain SUB=optional; "
            "run after final for stem evidence"
        ),
    }
    if write:
        rec = base / "receipts"
        rec.mkdir(parents=True, exist_ok=True)
        write_json(rec / "five-track-plan.json", report)
    return report


def audit_five_track(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Fail-closed when five_track enabled and hard issues present."""
    report = plan_five_track(root, write=write)
    if policy_skip_enabled():
        return {**report, "ok": True, "skipped": True}
    if report.get("enabled") and not report.get("ok"):
        codes = ",".join(report.get("codes") or [])
        raise FiveTrackError(f"five-track audit failed: {codes}. next: {report.get('next_cmd')}")
    return report
