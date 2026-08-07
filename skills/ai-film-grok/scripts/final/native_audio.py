"""Native I2V audio helpers (peeled from render_final · W4 residual)."""

from __future__ import annotations

import argparse
from typing import Any

from final.errors import RenderError

DEFAULT_NATIVE_AUDIO_VOLUME = 0.72
NATIVE_AUDIO_TARGET_DB = -22.0
NATIVE_AUDIO_GAIN_MIN = 0.50
NATIVE_AUDIO_GAIN_MAX = 1.60

# H3 原声轻处理（P0 · 2026-08-07）— single source; 禁默认 agate / 双 arnndn
# memory: 2026-08-07-h3-native-speech-isolate · no-midframe-composite-flf-audio
NATIVE_LIGHT_AF_FILTER = (
    "highpass=f=80,lowpass=f=12000,afftdn=nr=12:nf=-25,adeclick,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)
NATIVE_LIGHT_AF_FILTER_NO_AGATE = NATIVE_LIGHT_AF_FILTER  # alias: never agate by default
FILM_NATIVE_STABLE_BASENAME = "film_native_stable.mp4"
FILM_NATIVE_SPEECH_BROKEN_BASENAME = "film_native_speech_BROKEN_gate.mp4"


def resolve_native_audio_volume(
    args: argparse.Namespace,
    spec: dict[str, Any],
    voice_policy: dict[str, Any] | None = None,
) -> float:
    """Resolve native I2V audio gain without letting a policy override the CLI."""
    cli_value = getattr(args, "native_audio_volume", None)
    if cli_value is not None:
        raw_value = cli_value
    elif (voice_policy or {}).get("native_audio_volume") is not None:
        raw_value = (voice_policy or {})["native_audio_volume"]
    else:
        raw_value = spec.get("native_audio_volume", DEFAULT_NATIVE_AUDIO_VOLUME)
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise RenderError("native_audio_volume must be between 0 and 1") from exc
    if value < 0 or value > 1:
        raise RenderError("native_audio_volume must be between 0 and 1")
    return value


def primary_native_shot_ids(shot_audio: list[dict[str, Any]]) -> list[str]:
    """Keep usable native ambience, never a stem replaced by rendered TTS."""
    return [
        str(item["id"])
        for item in shot_audio
        if item.get("native_audio")
        and item.get("native_audio_audible") is not False
        and not item.get("native_audio_suppressed_for_tts")
    ]


def native_dialogue_replaced_by_post_tts(shot: dict[str, Any]) -> bool:
    """True only when an approved dialogue contract explicitly selects post TTS."""
    contracts = shot.get("dialogue_contracts")
    if not isinstance(contracts, list):
        return False
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        for line in contract.get("lines") or []:
            if isinstance(line, dict) and str(line.get("audio_origin") or "") == "post_vo":
                return True
    return False


def _contract_audio_origins(shot: dict[str, Any]) -> set[str]:
    origins: set[str] = set()
    contracts = shot.get("dialogue_contracts")
    if not isinstance(contracts, list):
        return origins
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        for line in contract.get("lines") or []:
            if isinstance(line, dict):
                origin = str(line.get("audio_origin") or "").strip().lower()
                if origin:
                    origins.add(origin)
    return origins


def _force_strip_native_policy(
    shot: dict[str, Any],
    *,
    audio_policy: str | None = None,
) -> bool:
    """True when policy explicitly replaces native dialogue with post TTS/BGM."""
    candidates: list[str] = []
    if audio_policy:
        candidates.append(str(audio_policy))
    for key in ("audio_policy", "h3_audio_policy", "native_audio_policy"):
        raw = shot.get(key)
        if isinstance(raw, dict):
            candidates.append(str(raw.get("mode") or raw.get("audio_policy") or ""))
        elif raw is not None:
            candidates.append(str(raw))
    for value in candidates:
        token = value.strip().lower()
        if token in {"strip_native_use_tts_bgm", "mute_native", "post_tts", "adr"}:
            return True
    return False


def resolve_dialogue_audio_lane(
    shot: dict[str, Any],
    *,
    has_native_stem: bool,
    native_audible: bool | None,
    has_spoken_text: bool,
    non_vo_coverage: bool = False,
    audio_policy: str | None = None,
) -> str:
    """Pick exactly one dialogue audio lane: native XOR post_tts XOR silence.

    Never returns a lane that would mix audible native dialogue with Edge TTS
    for the same spoken line (double-speak disaster).
    """
    # Explicit field wins when already planned (Wave 2 honesty)
    explicit = str(shot.get("dialogue_audio_lane") or "").strip().lower()
    if explicit in {"native", "post_tts", "silence"}:
        if explicit == "native" and _force_strip_native_policy(
            shot, audio_policy=audio_policy
        ):
            return "post_tts" if has_spoken_text else "silence"
        return explicit

    if non_vo_coverage and not has_spoken_text:
        return "silence"

    origins = _contract_audio_origins(shot)
    force_strip = _force_strip_native_policy(shot, audio_policy=audio_policy)
    usable_native = bool(has_native_stem) and native_audible is not False

    if force_strip or "post_vo" in origins:
        if has_spoken_text:
            return "post_tts"
        return "silence"

    if "native" in origins and usable_native:
        return "native"

    if usable_native and has_spoken_text:
        return "native"

    if has_spoken_text:
        return "post_tts"

    return "silence"


def _shot_has_spoken_for_lane(shot: dict[str, Any]) -> bool:
    if str(shot.get("spoken_text") or "").strip():
        return True
    for cue in shot.get("audio_cues") or []:
        if not isinstance(cue, dict):
            continue
        if str(cue.get("spoken_text") or cue.get("text") or "").strip():
            lt = str(cue.get("line_type") or "dialogue").strip().lower()
            if lt not in {"sfx", "ambience", "music", "bed", "foley", "narration"}:
                return True
    sm = str(shot.get("screen_mode") or "").strip().lower()
    return sm in {"on_camera", "off_camera", "on-camera", "off-camera"} and bool(
        str(shot.get("dialogue") or shot.get("dialogue_zh") or "").strip()
    )


def plan_default_dialogue_audio_lane(shot: dict[str, Any], *, profile: str | None = None) -> str:
    """Plan-time default when field missing: h3/native prefer_native for spoken."""
    if not _shot_has_spoken_for_lane(shot):
        return "silence"
    explicit = str(shot.get("dialogue_audio_lane") or "").strip().lower()
    if explicit in {"native", "post_tts", "silence"}:
        return explicit
    # Restricted / on_camera → native (H3/Grok); else still prefer native with TTS fallback at mix
    sm = str(shot.get("screen_mode") or "").strip().lower()
    if sm in {"on_camera", "on-camera", ""}:
        return "native"
    return "native"


def apply_film_dialogue_audio_lanes(spec: dict[str, Any]) -> dict[str, Any]:
    """Mutate shots: fill missing dialogue_audio_lane for spoken dialogue shots."""
    if not isinstance(spec, dict):
        return {"ok": False, "applied": 0}
    applied = 0
    missing_before = 0
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            if not _shot_has_spoken_for_lane(shot):
                continue
            if not str(shot.get("dialogue_audio_lane") or "").strip():
                missing_before += 1
                shot["dialogue_audio_lane"] = plan_default_dialogue_audio_lane(shot)
                applied += 1
    if isinstance(spec.get("shots"), list):
        for shot in spec["shots"]:
            if not isinstance(shot, dict):
                continue
            if not _shot_has_spoken_for_lane(shot):
                continue
            if not str(shot.get("dialogue_audio_lane") or "").strip():
                missing_before += 1
                shot["dialogue_audio_lane"] = plan_default_dialogue_audio_lane(shot)
                applied += 1
    report = {
        "ok": True,
        "applied": applied,
        "missing_before": missing_before,
        "note": "dialogue_audio_lane ∈ native|post_tts|silence (XOR at final mix)",
    }
    spec["_dialogue_audio_lanes"] = report
    return report


def lint_film_dialogue_audio_lanes(spec: dict[str, Any]) -> dict[str, Any]:
    """Spoken dialogue shots must declare dialogue_audio_lane (Wave 2 preflight)."""
    missing: list[str] = []
    invalid: list[str] = []
    checked = 0
    for scene in (spec.get("scenes") or []) if isinstance(spec, dict) else []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict) or not _shot_has_spoken_for_lane(shot):
                continue
            checked += 1
            sid = str(shot.get("id") or "?")
            lane = str(shot.get("dialogue_audio_lane") or "").strip().lower()
            if not lane:
                missing.append(sid)
            elif lane not in {"native", "post_tts", "silence"}:
                invalid.append(f"{sid}:{lane}")
    ok = not missing and not invalid
    return {
        "schema_version": 1,
        "kind": "dialogue-audio-lane-lint",
        "ok": ok,
        "checked": checked,
        "missing_lane_shots": missing,
        "invalid_lane_shots": invalid,
        "code": "DIALOGUE_AUDIO_LANE_MISSING" if missing else (
            "DIALOGUE_AUDIO_LANE_INVALID" if invalid else None
        ),
    }


def dialogue_lane_tts_mix_gain(lane: str) -> float:
    """Audible TTS only on post_tts lane; native/silence keep caption clock silent."""
    return 1.0 if str(lane or "").strip().lower() == "post_tts" else 0.0


def dialogue_lane_suppresses_native(lane: str) -> bool:
    return str(lane or "").strip().lower() == "post_tts"


def resolve_native_audio_gain(native_record: dict[str, Any] | None) -> float:
    """Normalize audible I2V stems conservatively; never amplify known silence."""
    if not isinstance(native_record, dict):
        return 1.0
    if native_record.get("audible") is False:
        return 0.0
    mean_volume_db = native_record.get("mean_volume_db")
    if not isinstance(mean_volume_db, (int, float)) or isinstance(mean_volume_db, bool):
        return 1.0
    gain = 10 ** ((NATIVE_AUDIO_TARGET_DB - float(mean_volume_db)) / 20)
    return max(NATIVE_AUDIO_GAIN_MIN, min(NATIVE_AUDIO_GAIN_MAX, gain))
