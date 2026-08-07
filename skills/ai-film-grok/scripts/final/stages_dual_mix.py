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



def run_dual_track_mix_stage(
    *,
    root: Path,
    work: Path,
    audio_dir: Path,
    args: Any,
    spec: dict[str, Any],
    shot_audio: list[dict[str, Any]],
    mood: str,
    vo_gain: float,
    native_audio_volume: float,
    music_path: Path,
    voice_cat: Path,
    native_track: Path,
    sfx_stereo_path: Path,
    scene_sound_path: Path,
    ambience_path: Path,
    ambience_volume: float,
    color_track: Path | None,
    mix_spotting: dict[str, Any],
    sound_plan: dict[str, Any] | None,
    formal_silence_windows: list[dict[str, Any]],
    formal_timeline: dict[str, Any] | None,
    run: Callable[..., Any],
    write_final_mix_partial_receipt: Callable[..., Any],
    summarize_bgm_response: Callable[..., Any] | None,
    build_music_mix_review: Callable[..., Any] | None,
    probe_mixed_loudness: Callable[..., Any],
    sha256: Callable[[Path], str],
    heartbeat: Callable[[str, str | None], None] | None = None,
    sample_rate_default: int = 44100,
) -> dict[str, Any]:
    """Stage 7: dual-track mix + loudnorm + stem export bookkeeping."""
    import json
    import os
    import shutil
    from pathlib import Path

    from final.errors import RenderError
    from final.render_defaults import SR
    from logger import log
    from security_policy import SecurityPolicyError, atomic_write_text, safe_output_path
    from sound_plan import (
        SoundPlanError,
        resolve_loudnorm,
        resolve_sidechain,
        should_apply_loudnorm,
        sidechain_filter_fragment,
        validate_audio_tracks_contract,
    )

    _hb = heartbeat or (lambda *_a, **_k: None)
    SR = sample_rate_default
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

    return {
        "mixed": mixed,
        "mix_spotting": mix_spotting,
        "music_vol": music_vol,
        "filters_help": filters_help,
        "preserved_native_shots": preserved_native_shots,
        "suppressed_native_shots": suppressed_native_shots,
        "use_color": use_color,
        "mix_sample_rate": mix_sample_rate,
    }
