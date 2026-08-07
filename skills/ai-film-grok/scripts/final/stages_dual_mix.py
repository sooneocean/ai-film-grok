"""Dual-track mix policy leaves (orchestrator relief W1 · structure only).

Keeps Wave D PARTIAL / broadband default / acrossover opt-in semantics.
No volume or sidechain threshold retune in this module.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path
from typing import Any, Callable


def env_flag_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def apply_mix_path_env_policy(
    filters_help: str,
    *,
    mix_spotting: dict[str, Any] | None = None,
) -> str:
    """Apply AIFILM_* mix path env flags; return (possibly rewritten) filters_help.

    Default: broadband duck (strip acrossover so sidechaincompress-only path runs).
    - AIFILM_FORCE_SIMPLE_AMIX → plain amix (no duck)
    - AIFILM_ALLOW_ACROSSOVER_MIX → legacy multiband sidechain
    - AIFILM_FORCE_BROADBAND_DUCK → explicit broadband (same as default)
    """
    spotting = mix_spotting if mix_spotting is not None else {}
    help_text = filters_help or ""
    if env_flag_on("AIFILM_FORCE_SIMPLE_AMIX"):
        spotting["force_simple_amix"] = True
        spotting["mix_path"] = "simple_amix"
        return ""
    if env_flag_on("AIFILM_ALLOW_ACROSSOVER_MIX"):
        spotting["allow_acrossover_mix"] = True
        spotting["mix_path"] = "acrossover_multiband"
        return help_text
    # Default + FORCE_BROADBAND: strip acrossover so sidechaincompress-only path runs
    help_text = help_text.replace("acrossover", "___disabled_acrossover___")
    spotting["force_broadband_duck"] = True
    spotting["mix_path"] = "broadband_default"
    if env_flag_on("AIFILM_FORCE_BROADBAND_DUCK"):
        spotting["force_broadband_duck_env"] = True
    return help_text


def dialogue_xor_violations(shot_audio: list[dict[str, Any]]) -> list[str]:
    """Fail-closed bookkeeping: native + audible TTS on the same shot."""
    violations = [
        item["id"]
        for item in shot_audio
        if item.get("dialogue_audio_lane") == "native"
        and float(item.get("tts_mix_gain") or 0.0) > 0.0
    ] + [
        item["id"]
        for item in shot_audio
        if item.get("dialogue_audio_lane") == "post_tts"
        and item.get("native_audio")
        and not item.get("native_audio_suppressed_for_tts")
        and item.get("native_audio_audible") is not False
    ]
    return sorted({str(x) for x in violations})


def run_sidechain_mix_with_amix_fallback(
    *,
    mix_cmd: list[str],
    voice_cat: Path | str,
    music_path: Path | str,
    native_track: Path | str,
    sfx_stereo_path: Path | str,
    scene_sound_path: Path | str,
    ambience_path: Path | str,
    color_track: Path | str | None,
    use_color: bool,
    mixed: Path,
    mix_sample_rate: int,
    mix_spotting: dict[str, Any],
    root: Path | str,
    run: Callable[..., Any],
    log: Callable[[str], None],
    write_partial_receipt: Callable[..., Path],
    render_error_cls: type[Exception],
) -> None:
    """Run primary mix_cmd; on sidechain failure fall back to simple amix PARTIAL."""
    try:
        run(mix_cmd)
        return
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as mix_exc:
        prior_sc = mix_spotting.get("sidechain_applied")
        if not prior_sc:
            raise render_error_cls(
                f"audio mix failed (no sidechain to fall back from): {mix_exc}"
            ) from mix_exc
        log(
            f"sidechain mix failed ({type(mix_exc).__name__}) → simple amix PARTIAL "
            f"(was {prior_sc!r})"
        )
        with contextlib.suppress(OSError):
            if mixed.is_file():
                mixed.unlink()
        color_in = "[6:a]" if use_color else ""
        n_in = 6 + (1 if use_color else 0)
        simple_fc = (
            f"[0:a][1:a][2:a][3:a][4:a][5:a]{color_in}"
            f"amix=inputs={n_in}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        simple_cmd: list[str] = [
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
        if use_color and color_track is not None:
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
            raise render_error_cls(
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
        try:
            partial_path = write_partial_receipt(
                root,
                prior_sc=str(prior_sc),
                error=str(mix_exc),
                mixed=mixed,
            )
            mix_spotting["partial_receipt"] = str(partial_path)
        except Exception as rec_exc:  # noqa: BLE001
            mix_spotting["partial_receipt_error"] = str(rec_exc)[:160]
