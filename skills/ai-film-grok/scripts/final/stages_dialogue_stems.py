"""Per-shot dialogue stems — **H3/native primary**, Edge TTS escape only (W1.5).

Product truth (hard-defaults · 原声 XOR TTS):
- H3 / Grok dialogue: **listen to clip native audio** (prefer_native).
- VO stem on ``native`` lane is a **silent caption clock** — never Edge double-speak.
- ``post_tts`` only when policy/contract forces strip_native / post_vo / ADR.
- ``silence`` for non-VO coverage plates.

Peels *lane planning* + *silent clock materialize*. Edge synthesis stays in
render_final as an escape hatch only — not expanded by this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from final.native_audio import (
    dialogue_lane_suppresses_native,
    dialogue_lane_tts_mix_gain,
    native_dialogue_replaced_by_post_tts,
    resolve_dialogue_audio_lane,
)
from final.render_helpers import resolve_plate_slot_sec
from logger import log
from security_policy import SecurityPolicyError, safe_output_path


@dataclass(frozen=True)
class DialogueStemPlan:
    """Machine plan for one shot's dialogue mix lane (XOR)."""

    lane: str  # native | post_tts | silence
    tts_mix_gain: float
    caption_clock_only: bool
    native_suppressed: bool
    film_audio_policy: str
    non_vo_coverage: bool
    needs_edge_tts: bool
    note: str


def resolve_film_audio_policy(spec: dict[str, Any] | None) -> str:
    """Film-level audio_policy string (prefer_native is the default lane path)."""
    if not isinstance(spec, dict):
        return ""
    _ap = spec.get("audio_policy")
    _h3 = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
    if isinstance(_ap, dict):
        return str(
            _ap.get("mode") or _ap.get("audio_policy") or _h3.get("audio_policy") or ""
        )
    return str(_ap or _h3.get("audio_policy") or "")


def plan_dialogue_stem(
    shot: dict[str, Any],
    *,
    has_native_stem: bool,
    native_audible: bool | None,
    spoken_text: str,
    non_vo_coverage: bool,
    film_audio_policy: str | None = None,
) -> DialogueStemPlan:
    """Pick XOR lane; Edge TTS only when lane is post_tts and text is present."""
    text = str(spoken_text or "").strip()
    lane = resolve_dialogue_audio_lane(
        shot,
        has_native_stem=has_native_stem,
        native_audible=native_audible,
        has_spoken_text=bool(text),
        non_vo_coverage=non_vo_coverage,
        audio_policy=film_audio_policy or None,
    )
    native_suppressed = bool(has_native_stem) and dialogue_lane_suppresses_native(lane)
    if native_dialogue_replaced_by_post_tts(shot) and lane != "post_tts":
        lane = "post_tts"
        native_suppressed = bool(has_native_stem)
    tts_mix_gain = dialogue_lane_tts_mix_gain(lane)
    caption_clock_only = lane == "native"
    needs_edge = lane == "post_tts" and bool(text)
    if non_vo_coverage or lane == "silence":
        note = "non_vo_coverage" if non_vo_coverage else "silence_lane"
    elif lane == "native":
        note = "native_xor_caption_clock"
    elif needs_edge:
        note = "post_tts_escape"
    else:
        note = f"lane={lane}"
    return DialogueStemPlan(
        lane=lane,
        tts_mix_gain=tts_mix_gain,
        caption_clock_only=caption_clock_only,
        native_suppressed=native_suppressed,
        film_audio_policy=str(film_audio_policy or ""),
        non_vo_coverage=bool(non_vo_coverage),
        needs_edge_tts=needs_edge,
        note=note,
    )


def materialize_silent_vo_clock(
    *,
    sid: str,
    index: int,
    shot: dict[str, Any],
    work: Path,
    audio_dir: Path,
    lane: str,
    note: str,
    silence_wav: Callable[[Path, float], None],
    run: Callable[..., Any],
    render_error_cls: type[Exception],
) -> dict[str, Any]:
    """Silent VO clock for native caption-clock or silence lanes. Never Edge."""
    plate_slot = resolve_plate_slot_sec(shot)
    if lane == "native":
        silent_wav = work / f"vo_native_clock_{index:02d}_{sid}.wav"
        log_msg = (
            f"native dialogue {sid}: keep clip audio, silent VO clock "
            f"{plate_slot:.2f}s (caption only; no Edge double-speak)"
        )
        meta_note = "native_xor_caption_clock"
    else:
        silent_wav = work / f"vo_silent_{index:02d}_{sid}.wav"
        log_msg = f"silence VO {sid}: coverage plate {plate_slot:.2f}s (no TTS)"
        meta_note = note if note in {"non_vo_coverage", "silence_lane"} else "silence_lane"

    try:
        mp3 = safe_output_path(
            audio_dir, f"{sid}_vo.mp3", suffixes={".mp3"}, field=f"VO output for {sid}"
        )
        safe_output_path(
            audio_dir, f"{sid}_vo.wav", suffixes={".wav"}, field=f"VO WAV output for {sid}"
        )
    except SecurityPolicyError as exc:
        raise render_error_cls(str(exc)) from exc

    silence_wav(silent_wav, plate_slot)
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
    log(log_msg)
    tts_meta: dict[str, Any] = {
        "backend": "silence",
        "voice": "none",
        "note": meta_note,
        "duration_sec": plate_slot,
    }
    if lane == "native":
        tts_meta["dialogue_audio_lane"] = "native"
    return {
        "wav": silent_wav,
        "mp3": mp3,
        "dur": plate_slot,
        "tts_meta": tts_meta,
        "shot_voice": "none",
        "shot_tts_backend": "silence",
        "clear_spoken": lane != "native",
    }
