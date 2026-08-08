"""BGM seed / anti-fatigue / bed materialize leaves (orchestrator relief W1.2).

Structure-only peel from render_final music stage. No volume/policy retune.
"""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path
from typing import Any, Callable

import numpy as np
from logger import log
from util import write_json


def resolve_music_seed(
    *,
    args: Any,
    spec: dict[str, Any],
    root: Path,
    mood: str,
    total_dur: float,
) -> tuple[int, dict[str, Any], str]:
    """CLI > audio_policy.music_seed > stable title|mood|dur hash.

    Returns (music_seed, audio_policy, mood) where mood may be overridden by
    sound_plan.mood when callers pass plan_mood via the returned mood only if
    they already applied plan_mood — this helper does not read sound_plan.
    """
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
        route = spec.get("_audio_routing") if isinstance(spec.get("_audio_routing"), dict) else {}
        counts = route.get("counts") if isinstance(route.get("counts"), dict) else {}
        count_key = ",".join(f"{k}{counts.get(k, 0)}" for k in sorted(counts))
        raw_seed = f"{title_s}|{mood}|{total_dur:.2f}|v3-multi-style|{count_key}"
        music_seed = int(hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:8], 16)
    return music_seed, ap if isinstance(ap, dict) else {}, mood


def apply_plan_mood(mood: str, sound_plan: dict[str, Any] | None) -> str:
    plan_mood = (sound_plan or {}).get("mood") if sound_plan else None
    if plan_mood:
        return str(plan_mood)
    return mood


def run_bgm_anti_fatigue(
    *,
    root: Path,
    args: Any,
    sound_plan: dict[str, Any] | None,
    mix_spotting: dict[str, Any],
    mood: str,
    music_seed: int,
    total_dur: float,
    ap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Write anti-fatigue receipt into mix_spotting; return hard issues list."""
    hard_fat: list[dict[str, Any]] = []
    try:
        from bgm_anti_fatigue import check_bgm_anti_fatigue

        bed_src = str(ap.get("bed_source") or "auto")
        tmpl_preview = str(
            getattr(args, "music_template", None)
            or (sound_plan or {}).get("music_template")
            or "auto"
        )
        fatigue = check_bgm_anti_fatigue(
            root,
            total_dur_sec=float(total_dur),
            music_seed=music_seed,
            bed_source=bed_src,
            template_mode=tmpl_preview,
            mood=mood,
            write=True,
        )
        mix_spotting["bgm_anti_fatigue"] = {
            "ok": fatigue.get("ok"),
            "issues": fatigue.get("issues"),
            "recommend": fatigue.get("recommend"),
        }
        hard_fat = [
            i for i in (fatigue.get("issues") or []) if i.get("severity") == "hard"
        ]
        mix_spotting["bgm_anti_fatigue"]["hard_count"] = len(hard_fat)
        if hard_fat:
            log(
                "bgm anti-fatigue HARD: inject multi-chapter procedural motifs "
                f"(dur={total_dur:.0f}s)"
            )
            mix_spotting["bgm_anti_fatigue"]["auto_chapters"] = True
    except Exception as exc:  # noqa: BLE001
        mix_spotting["bgm_anti_fatigue"] = {"ok": True, "error": str(exc)[:120]}
        hard_fat = []
    return hard_fat


def enrich_sound_plan_music_timelines(
    *,
    sound_plan: dict[str, Any],
    mix_spotting: dict[str, Any],
    mood: str,
    total_dur: float,
    hard_fat: list[dict[str, Any]],
    shot_dicts: list[dict[str, Any]],
    shot_start_map: dict[str, float],
    shot_end_map: dict[str, float],
    build_mood_timeline: Callable[..., Any],
    build_music_timeline: Callable[..., Any] | None,
    summarize_music_timeline: Callable[..., Any] | None,
    render_error_cls: type[Exception],
) -> dict[str, Any]:
    """Attach mood/music timelines + optional anti-fatigue chapters to sound_plan."""
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
            if summarize_music_timeline is not None:
                mix_spotting["music_cue_routing"] = summarize_music_timeline(
                    sound_plan["music_timeline"]
                )
            sound_plan["mood_timeline"] = sound_plan["music_timeline"]
        except ValueError as exc:
            raise render_error_cls(f"invalid shot music_cue: {exc}") from exc
    if hard_fat or (
        float(total_dur) >= 180.0
        and (mix_spotting.get("bgm_anti_fatigue") or {}).get("auto_chapters")
    ):
        try:
            from bgm_anti_fatigue import inject_anti_fatigue_chapters

            base_tl = (
                sound_plan.get("music_timeline")
                or sound_plan.get("mood_timeline")
                or []
            )
            injected = inject_anti_fatigue_chapters(
                base_tl if isinstance(base_tl, list) else [],
                total_dur_sec=float(total_dur),
                default_mood=mood,
                chapter_sec=45.0,
            )
            sound_plan["mood_timeline"] = injected
            sound_plan["music_timeline"] = injected
            mix_spotting["bgm_anti_fatigue"] = {
                **(mix_spotting.get("bgm_anti_fatigue") or {}),
                "chapters_injected": len(injected),
                "auto_chapters": True,
            }
            log(f"bgm anti-fatigue: {len(injected)} chapters injected for procedural variety")
        except Exception as exc:  # noqa: BLE001
            log(f"bgm anti-fatigue chapter inject skip: {exc}")
    return sound_plan


def materialize_music_bed(
    *,
    root: Path,
    work: Path,
    args: Any,
    spec: dict[str, Any],
    sound_plan: dict[str, Any] | None,
    mix_spotting: dict[str, Any],
    mood: str,
    music_seed: int,
    total_dur: float,
    title_dur: float,
    shot_audio: list[dict[str, Any]],
    ap: dict[str, Any],
    apply_spotting: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray, dict[str, Any]]],
    resolve_music_template: Callable[..., Any],
    render_music_template_timeline: Callable[..., Any],
    try_external_music_gen: Callable[..., Any],
    procedural_music: Callable[..., Any],
    write_wav_stereo: Callable[..., Any],
    run: Callable[..., Any],
    sample_rate: int,
    default_bgm_gen_amp: float,
    render_error_cls: type[Exception],
    sound_plan_error_cls: type[Exception],
) -> dict[str, Any]:
    """Resolve template/user/procedural bed, apply spotting, write stereo WAVs + A4 receipt.

    Returns dict:
      music_path, sfx_stereo_path, license_note, mix_spotting, music_resolved,
      bgm_source_receipt, mood
    """
    bed_source = str(ap.get("bed_source") or "auto").lower()
    template_mode = str(
        getattr(args, "music_template", None)
        or ("approved_library" if bed_source == "approved_library" else None)
        or (sound_plan or {}).get("music_template")
        or "auto"
    ).lower()
    template_timeline_samples: np.ndarray | None = None
    template_timeline_selections: list[dict[str, Any]] = []
    music_resolved: dict[str, Any] | None
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
        except (sound_plan_error_cls, render_error_cls) as exc:
            raise render_error_cls(str(exc)) from exc
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
        except sound_plan_error_cls as exc:
            raise render_error_cls(str(exc)) from exc

    if music_resolved is None and template_timeline_samples is None:
        ext_music = try_external_music_gen(
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

    sfx_stereo_path: Path
    music_path: Path
    if template_timeline_samples is not None:
        license_note = (
            "approved shared BGM library; see mix_report music_template.selections"
            if template_mode == "approved_library"
            else "timeline of licensed local BGM templates; see mix_report music_template.selections"
        )
        user_f, sfx_f, spotting_only = apply_spotting(template_timeline_samples)
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
                str(sample_rate),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(mono_tmp),
            ]
        )
        with wave.open(str(mono_tmp), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            user_i16 = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32767.0
        user_f, sfx_f, spotting_only = apply_spotting(user_i16)
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
        license_note = (
            "original generative numpy score (ai-film-grok procedural v3 multi-style, "
            "no third-party samples)"
        )
        gen_amp = float(getattr(args, "bgm_gen_amp", None) or default_bgm_gen_amp)
        bg_hint = 1.0
        try:
            bg_hint = float(
                (sound_plan or {}).get("bed_gain_hint")
                or (spec.get("_audio_routing") or {}).get("mean_bed_gain")
                or 1.0
            )
        except (TypeError, ValueError):
            bg_hint = 1.0
        s_starts: list[float] = []
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
        float_bed, sfx_f, spotting_only = apply_spotting(float_bed)
        mix_spotting = {**mix_spotting, **spotting_only}
        mix_spotting["bed_source"] = "procedural"
        mix_spotting["music_seed"] = music_seed
        mix_spotting["bed_gain_hint"] = bg_hint
        try:
            from make_sfx_bed import last_rnb_style, pick_rnb_style  # type: ignore

            mix_spotting["procedural_style"] = last_rnb_style() or pick_rnb_style(music_seed)
        except Exception:  # noqa: BLE001
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

    bgm_source_receipt: dict[str, Any] | None = None
    try:
        from sound_plan import build_bgm_source_receipt, mood_library_status

        bed_src = str(mix_spotting.get("bed_source") or "unknown")
        mood_st = mood_library_status(mood, film_root=root)
        bgm_source_receipt = build_bgm_source_receipt(
            bed_source=bed_src,
            mood=mood,
            license_note=str(license_note or ""),
            music_resolved=music_resolved if isinstance(music_resolved, dict) else None,
            mood_status=mood_st,
        )
        write_json(root / "receipts" / "bgm-source.json", bgm_source_receipt)
        mix_spotting["bgm_source_receipt"] = {
            "bed_source": bgm_source_receipt.get("bed_source"),
            "partial": bgm_source_receipt.get("partial"),
            "honest_limits": bgm_source_receipt.get("honest_limits"),
            "mood_library": bgm_source_receipt.get("mood_library"),
        }
        if bgm_source_receipt.get("partial"):
            log(
                "BGM honesty: "
                + "; ".join(str(x) for x in (bgm_source_receipt.get("honest_limits") or [])[:3])
            )
    except Exception as bgm_exc:  # noqa: BLE001 — never block final on receipt
        log(f"bgm-source receipt skip: {bgm_exc}")

    return {
        "music_path": music_path,
        "sfx_stereo_path": sfx_stereo_path,
        "license_note": license_note,
        "mix_spotting": mix_spotting,
        "music_resolved": music_resolved,
        "bgm_source_receipt": bgm_source_receipt,
        "mood": mood,
    }
