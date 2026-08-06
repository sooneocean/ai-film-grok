#!/usr/bin/env python3
"""VO atempo fit-to-plate (cn three-axis: video fixed, voice adjusts).

Architecture (ai-film-cn 坑#29 + 2026-07-20 星声·谢幕后 drag lesson):
  1) Video plate stays at duration_sec (no stretch-to-VO / stream_loop to fill speech)
  2) Voice uses ffmpeg atempo so fitted_dur ≈ plate (factor = vo / plate)
  3) Subtitles / pads lock to the same plate clock
  4) **Drag guard**: if VO is much shorter than plate, **pad silence** — do NOT slow
     speech with atempo≪1 (sounds 卡/拖腔). See lessons-2026-07-20-vo-drag-motion-snap.md

Direction trap: atempo > 1 speeds up (shortens); atempo < 1 slows (lengthens).
  fitted_sec = vo_sec / atempo
  so atempo = vo_sec / plate_sec  (od / target)

Choppy guard: clamp speedup atempo to [1, MAX] with MAX default 1.5.
If still over plate after max speedup → fail (fix nar / raise duration_sec), never choppy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env

# cn-proven defaults (tts_backends_atempo.md): max 1.5x; bias optional snappier speech
DEFAULT_MAX_ATEMPO = 1.5
DEFAULT_SPEED_BIAS = 1.0  # set 1.10 for slightly faster narration preference
# Below this factor, slowing speech to fill plate is banned → pad instead (星声 lesson)
DEFAULT_MIN_NATURAL_ATEMPO = 0.92
# ffmpeg atempo supports ~0.5–2.0 per filter; we stay inside 1/1.5–1.5 for speedup path
ATEMPO_FILTER_MIN = 0.5
ATEMPO_FILTER_MAX = 2.0


class VoAtempoError(RuntimeError):
    pass


def plan_vo_atempo(
    vo_sec: float,
    plate_sec: float,
    *,
    max_atempo: float = DEFAULT_MAX_ATEMPO,
    min_atempo: float | None = None,
    min_natural_atempo: float = DEFAULT_MIN_NATURAL_ATEMPO,
    speed_bias: float = DEFAULT_SPEED_BIAS,
    over_slack_sec: float = 0.05,
    allow_speech_drag: bool = False,
) -> dict[str, Any]:
    """Plan how to fit VO duration to a fixed plate.

    Returns:
      atempo: factor to pass to ffmpeg
      raw_atempo: unclamped vo/plate * bias
      fitted_sec: duration after atempo (before pad/trim)
      pad_sec: silence to append if still short
      out_sec: always plate_sec when ok
      clamp_hit: True if raw was outside [min,max]
      mode: "identity" | "atempo" | "atempo_pad" | "pad_natural" | "fail_over"
      ok: False only when VO cannot fit without exceeding max_atempo
      drag_guard: True when short VO was padded instead of slowed
    """
    if vo_sec <= 0:
        raise VoAtempoError(f"vo_sec must be > 0, got {vo_sec}")
    if plate_sec <= 0:
        raise VoAtempoError(f"plate_sec must be > 0, got {plate_sec}")
    max_a = float(max_atempo)
    if max_a < 1.0:
        raise VoAtempoError(f"max_atempo must be >= 1.0, got {max_a}")
    min_a = float(min_atempo) if min_atempo is not None else 1.0 / max_a
    if min_a <= 0 or min_a > 1.0:
        raise VoAtempoError(f"min_atempo must be in (0, 1], got {min_a}")
    min_nat = float(min_natural_atempo)
    if min_nat <= 0 or min_nat > 1.0:
        raise VoAtempoError(f"min_natural_atempo must be in (0, 1], got {min_nat}")

    bias = float(speed_bias) if speed_bias and speed_bias > 0 else 1.0
    raw = (float(vo_sec) / float(plate_sec)) * bias

    # --- Drag guard (星声·谢幕后 2026-07-20): short VO must not drag speech ---
    # raw < 1 means VO shorter than plate; raw < min_nat means we'd slow >~8%.
    if (not allow_speech_drag) and raw < min_nat and raw < 1.0 - 1e-9:
        fitted = float(vo_sec)
        pad = max(0.0, float(plate_sec) - fitted)
        return {
            "ok": True,
            "mode": "pad_natural",
            "atempo": 1.0,
            "raw_atempo": round(raw, 6),
            "vo_sec": float(vo_sec),
            "plate_sec": float(plate_sec),
            "fitted_sec": round(fitted, 4),
            "pad_sec": round(pad, 4),
            "out_sec": float(plate_sec),
            "clamp_hit": False,
            "drag_guard": True,
            "speed_bias": bias,
            "max_atempo": max_a,
            "min_atempo": min_a,
            "min_natural_atempo": min_nat,
            "note": (
                f"VO {vo_sec:.2f}s << plate {plate_sec:.2f}s (raw atempo={raw:.3f}<{min_nat}); "
                "pad silence, do not slow speech (vo-drag lesson). "
                "Prefer visual_fit:vo or longer nar for full 60s without dead air."
            ),
        }

    factor = max(min_a, min(max_a, raw))
    # Keep factor inside single-filter ffmpeg range
    factor = max(ATEMPO_FILTER_MIN, min(ATEMPO_FILTER_MAX, factor))
    clamp_hit = abs(raw - factor) > 1e-6
    fitted = float(vo_sec) / factor

    # Still longer than plate after max speedup → cannot fit without choppy
    if fitted > float(plate_sec) + float(over_slack_sec) and raw > max_a + 1e-9:
        return {
            "ok": False,
            "mode": "fail_over",
            "atempo": factor,
            "raw_atempo": round(raw, 6),
            "vo_sec": float(vo_sec),
            "plate_sec": float(plate_sec),
            "fitted_sec": round(fitted, 4),
            "pad_sec": 0.0,
            "out_sec": float(plate_sec),
            "clamp_hit": True,
            "drag_guard": False,
            "speed_bias": bias,
            "max_atempo": max_a,
            "min_atempo": min_a,
            "min_natural_atempo": min_nat,
            "note": (
                f"VO {vo_sec:.2f}s cannot fit plate {plate_sec:.2f}s within "
                f"atempo≤{max_a} (would need {raw:.3f}). Shorten nar or raise duration_sec."
            ),
        }

    pad = max(0.0, float(plate_sec) - fitted)
    if abs(factor - 1.0) < 0.01 and pad < 0.03:
        mode = "identity"
        factor = 1.0
        fitted = float(vo_sec)
        pad = max(0.0, float(plate_sec) - fitted)
    elif pad > 0.03:
        mode = "atempo_pad"
    else:
        mode = "atempo"

    return {
        "ok": True,
        "mode": mode,
        "atempo": round(factor, 6),
        "raw_atempo": round(raw, 6),
        "vo_sec": float(vo_sec),
        "plate_sec": float(plate_sec),
        "fitted_sec": round(fitted, 4),
        "pad_sec": round(pad, 4),
        "out_sec": float(plate_sec),
        "clamp_hit": clamp_hit,
        "drag_guard": False,
        "speed_bias": bias,
        "max_atempo": max_a,
        "min_atempo": min_a,
        "min_natural_atempo": min_nat,
        "note": "video plate fixed; VO atempo to plate (cn three-axis)",
    }


def atempo_filter_chain(factor: float) -> str:
    """Build ffmpeg af atempo chain (single stage when in [0.5, 2.0])."""
    f = float(factor)
    if f <= 0:
        raise VoAtempoError(f"invalid atempo factor {f}")
    # Chain if outside single-filter range (defensive; plan clamps to 0.5–1.5)
    parts: list[str] = []
    remaining = f
    # Reduce by multiplying filters in (0.5, 2.0]
    guard = 0
    while remaining > ATEMPO_FILTER_MAX + 1e-9 and guard < 8:
        parts.append(f"atempo={ATEMPO_FILTER_MAX}")
        remaining /= ATEMPO_FILTER_MAX
        guard += 1
    while remaining < ATEMPO_FILTER_MIN - 1e-9 and guard < 8:
        parts.append(f"atempo={ATEMPO_FILTER_MIN}")
        remaining /= ATEMPO_FILTER_MIN
        guard += 1
    parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def fit_voice_to_plate(
    wav_in: Path,
    wav_out: Path,
    plate_sec: float,
    *,
    vo_sec: float | None = None,
    plan: dict[str, Any] | None = None,
    max_atempo: float = DEFAULT_MAX_ATEMPO,
    speed_bias: float = DEFAULT_SPEED_BIAS,
    sample_rate: int = 48000,
) -> dict[str, Any]:
    """Apply atempo (+ optional silence pad) so output duration == plate_sec.

    If plan is provided it is used; else computed from vo_sec or probe.
    """
    wav_in = Path(wav_in)
    wav_out = Path(wav_out)
    if not wav_in.is_file():
        raise VoAtempoError(f"VO wav missing: {wav_in}")

    if plan is None:
        if vo_sec is None:
            from media_duration import probe_duration_sec

            vo_sec = probe_duration_sec(wav_in, label="vo_atempo_in")
        plan = plan_vo_atempo(
            float(vo_sec),
            float(plate_sec),
            max_atempo=max_atempo,
            speed_bias=speed_bias,
        )
    if not plan.get("ok"):
        raise VoAtempoError(plan.get("note") or "VO cannot fit plate with atempo")

    factor = float(plan["atempo"])
    plate = float(plan["plate_sec"])
    af_parts: list[str] = []
    if abs(factor - 1.0) >= 0.01:
        af_parts.append(atempo_filter_chain(factor))
    # Pad then hard-trim to exact plate (trim also covers tiny overshoot)
    af_parts.append(f"apad=pad_dur={max(plate, 0.05):.3f}")
    af_parts.append(f"atrim=0:{plate:.3f}")
    af_parts.append("asetpts=PTS-STARTPTS")
    af = ",".join(af_parts)

    wav_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_in),
        "-af",
        af,
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(wav_out),
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=minimal_subprocess_env(),
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise VoAtempoError("ffmpeg not found for vo atempo") from exc
    except subprocess.TimeoutExpired as exc:
        raise VoAtempoError(f"ffmpeg atempo timed out on {wav_in}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-400:]
        raise VoAtempoError(f"ffmpeg atempo failed (rc={proc.returncode}): {err}")

    out_plan = dict(plan)
    out_plan["path"] = str(wav_out)
    out_plan["filter"] = af
    return out_plan
