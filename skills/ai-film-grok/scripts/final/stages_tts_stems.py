"""Per-shot TTS + H3 native XOR stems (orchestrator relief · H3 native chain).

Structure-only peel of render_final stage 1. Preserves:
- prefer_native XOR post_tts (never double dialogue)
- caption_clock_only silent Edge on native lane
- A2 口白窗 triangle for post_tts
- Chinese-only product path
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from audio_cues import AudioCueError, strict_tts_text
from final.caption_text import caption_text_for_shot, split_units, spoken_text_for_shot
from final.errors import RenderError
from final.media_ops import run
from final.native_audio import (
    dialogue_lane_suppresses_native,
    dialogue_lane_tts_mix_gain,
    native_dialogue_replaced_by_post_tts,
    resolve_dialogue_audio_lane,
    resolve_native_audio_gain,
)
from final.render_defaults import DEFAULT_SUB_MAX_CHARS, SR
from final.render_helpers import coerce_optional_float, resolve_plate_slot_sec
from final.voice import (
    normalize_cast_tts_backends,
    tts_backend_for_shot,
    validate_voice_language_locks,
    voice_for_shot,
)
from logger import log
from narrative_timeline import _is_non_vo_coverage_shot, validate_linear_narration
from security_policy import SecurityPolicyError, safe_existing_file, safe_output_path

try:
    from voice_tracks import resolve_shot_vocal_color
except ImportError:  # pragma: no cover
    resolve_shot_vocal_color = None  # type: ignore

try:
    from performance_cue import normalize_performance_cue
except ImportError:  # pragma: no cover
    normalize_performance_cue = None  # type: ignore


def build_shot_audio_stems(
    *,
    root: Path,
    shots: list[dict[str, Any]],
    clips_map: dict[str, Any],
    clips_dir: Path,
    audio_dir: Path,
    native_dir: Path,
    work: Path,
    args: Any,
    vo_mode: str,
    voice: str,
    cast_voices: dict[str, Any],
    vo_rate: str,
    vo_pitch: str,
    vo_tts_vol: str,
    tts_backend: str,
    tts_allow_network_fallback: bool,
    cast_tts_backends: dict[str, Any],
    film_vocal_color_gain: float,
    dialogue_spoken_lang: str,
    narration_spoken_lang: str,
    voice_policy: dict[str, Any],
    shot_voice_cues: dict[str, Any],
    spec: dict[str, Any],
    approved_clip_record: Callable[..., bool],
    sha256: Callable[[Path], str],
    validate_broll_visual_review: Callable[..., dict[str, Any]],
    extract_native_audio: Callable[..., Path | None],
    tts_to_wav: Callable[..., Any],
    silence_wav: Callable[..., None],
) -> list[dict[str, Any]]:
    """Build per-shot audio stem records (native XOR TTS + caption clock)."""
    # 1) Per-shot TTS
    validate_voice_language_locks(shots, dialogue_spoken_lang=dialogue_spoken_lang)
    validate_linear_narration(
        shots,
        vo_mode=vo_mode,
        dialogue_spoken_lang=dialogue_spoken_lang,
        narration_spoken_lang=narration_spoken_lang,
    )
    # H3 native / plate force path: file-on-disk + status candidate|approved enough
    # when AIFILM_FINAL_ALLOW_CANDIDATE_CLIPS / force_allow_clips (post lipsync freeze).
    force_allow_clips = os.environ.get("AIFILM_FINAL_ALLOW_CANDIDATE_CLIPS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not force_allow_clips:
        try:
            from core.skip_audit import skip_flag

            force_allow_clips = skip_flag(
                "AIFILM_SKIP_DIALOGUE_PACKAGE_GATE",
                origin="env",
                film_root=root,
                call_site="render_final.force_allow_clips",
            )
        except Exception:
            force_allow_clips = os.environ.get(
                "AIFILM_SKIP_DIALOGUE_PACKAGE_GATE", ""
            ).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
    shot_audio: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        sid = shot["id"]
        rec = clips_map.get(sid)
        if not isinstance(rec, dict):
            raise RenderError(f"Clip {sid} missing from manifest")
        st = str(rec.get("status") or "").lower()
        if force_allow_clips:
            if st not in {"approved", "candidate"} or not rec.get("path"):
                raise RenderError(
                    f"Clip {sid} not usable on plate path (need approved|candidate + path)"
                )
        elif not approved_clip_record(rec):
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
            # Music Director desk: prefer directed stem (mute windows / peak) when apply receipt ok.
            try:
                from music_director import resolve_directed_native_path

                directed = resolve_directed_native_path(
                    root, str(sid), source_path=native_audio
                )
                if directed is not None:
                    native_audio = directed
                    native_audio_gain = 1.0
            except Exception:
                pass
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
        # dialogue_drama coverage may carry no spoken line — plate ambience only.
        non_vo_coverage = _is_non_vo_coverage_shot(shot) and not text
        # W1.5 · H3/native primary (leaf: final.stages_dialogue_stems)
        # Edge TTS is post_tts escape only — never double-speak over H3 native.
        from final.stages_dialogue_stems import (
            materialize_silent_vo_clock,
            plan_dialogue_stem,
            resolve_film_audio_policy,
        )

        film_audio_policy = resolve_film_audio_policy(spec if isinstance(spec, dict) else {})
        _stem = plan_dialogue_stem(
            shot,
            has_native_stem=native_audio is not None,
            native_audible=native_audio_audible,
            spoken_text=str(text or ""),
            non_vo_coverage=non_vo_coverage,
            film_audio_policy=film_audio_policy or None,
        )
        dialogue_audio_lane = _stem.lane
        native_dialogue_replaced = _stem.native_suppressed
        tts_mix_gain = _stem.tts_mix_gain
        caption_clock_only = _stem.caption_clock_only
        max_chars = int(
            getattr(args, "sub_max_chars", DEFAULT_SUB_MAX_CHARS) or DEFAULT_SUB_MAX_CHARS
        )
        units = split_units(caption_text, max_len=max_chars) if caption_text else []
        if not _stem.needs_edge_tts:
            clock = materialize_silent_vo_clock(
                sid=sid,
                index=i,
                shot=shot,
                work=work,
                audio_dir=audio_dir,
                lane=(
                    dialogue_audio_lane
                    if dialogue_audio_lane in {"native", "silence"}
                    else "silence"
                ),
                note=_stem.note,
                silence_wav=silence_wav,
                run=run,
                render_error_cls=RenderError,
            )
            wav = clock["wav"]
            mp3 = clock["mp3"]
            dur = clock["dur"]
            tts_meta = clock["tts_meta"]
            shot_voice = clock["shot_voice"]
            shot_tts_backend = clock["shot_tts_backend"]
            if clock["clear_spoken"]:
                text = ""
                caption_text = ""
                units = []
            color_wav = None
            color_dur = 0.0
            color_meta = None
            color_payload = {}
            color_text = ""
            color_gain = 0.0
        else:
            # post_tts escape only (not H3 native default)
            try:
                mp3 = safe_output_path(
                    audio_dir, f"{sid}_vo.mp3", suffixes={".mp3"}, field=f"VO output for {sid}"
                )
                safe_output_path(
                    audio_dir, f"{sid}_vo.wav", suffixes={".wav"}, field=f"VO WAV output for {sid}"
                )
            except SecurityPolicyError as exc:
                raise RenderError(str(exc)) from exc
            if not text:
                raise RenderError(
                    f"Shot {sid} has no spoken text for post_tts escape "
                    f"(need Chinese nar/dialogue/caption_text or voice.spoken_text)"
                )
            log(f"post_tts escape {sid}: {text[:40]}...")
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
                f"dur={dur:.2f}s lane=post_tts"
            )
            # Independent 娇喘/语助词 stem (not mixed into nar text)
            color_wav: Path | None = None
            color_dur = 0.0
            color_meta: dict[str, Any] | None = None
            color_payload: dict[str, Any] = {}
        if (
            not non_vo_coverage
            and dialogue_audio_lane == "post_tts"
            and resolve_shot_vocal_color is not None
            and voice_policy.get("enabled", False)
        ):
            try:
                color_payload = resolve_shot_vocal_color(shot, policy=voice_policy, seed=i * 17)
            except Exception:
                color_payload = {}
        if not non_vo_coverage and dialogue_audio_lane == "post_tts":
            color_text = str(color_payload.get("text") or "").strip()
            color_gain = float(color_payload.get("gain") or film_vocal_color_gain or 0.0)
        if (
            (not non_vo_coverage)
            and dialogue_audio_lane == "post_tts"
            and color_text
            and color_gain > 0
            and film_vocal_color_gain > 0
        ):
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
        # A2 · 2026-08-06: 口白窗三角 — offset+cue≤slot; TTS≤cue; try atempo→cue before fail.
        cue_offset = float(voice_cue.get("start_offset_sec") or 0.0) if voice_cue else 0.0
        cue_window = float(voice_cue.get("duration_sec") or 0.0) if voice_cue else 0.0
        _slot_for_cue = resolve_plate_slot_sec(shot, default=0.0, min_sec=0.0)
        # Native/silence: VO stem is silent plate clock — skip Edge cue triangle.
        if voice_cue and _slot_for_cue > 0 and dialogue_audio_lane == "post_tts":
            from final.voice import check_vo_window_triangle

            tri_ok, tri_code = check_vo_window_triangle(
                float(dur), cue_offset, cue_window, _slot_for_cue
            )
            if tri_code == "cue_exceeds_slot":
                raise RenderError(
                    f"{sid} voice cue exceeds plate "
                    f"(offset {cue_offset:.2f}+cue {cue_window:.2f} > slot {_slot_for_cue:.2f}); "
                    "shrink cue duration or raise duration_sec — do not invent cues past slot"
                )
            if tri_code == "tts_exceeds_cue":
                vo_fit_early = str(
                    spec.get("vo_fit") or getattr(args, "vo_fit", None) or "atempo"
                ).strip().lower()
                if vo_fit_early == "atempo" and cue_window > 0:
                    try:
                        from vo_atempo import VoAtempoError, fit_voice_to_plate, plan_vo_atempo

                        plan = plan_vo_atempo(float(dur), float(cue_window))
                        if not plan.get("ok"):
                            raise RenderError(
                                f"{sid} voice cue exceeds reserved window even after atempo "
                                f"({dur:.2f}s > {cue_window:.2f}s; {plan.get('note')}); "
                                "shorten spoken / raise vo_rate / enlarge cue within slot"
                            )
                        fitted_cue = work / f"vo_cue_fit_{i:02d}_{sid}.wav"
                        fit_voice_to_plate(
                            wav,
                            fitted_cue,
                            float(cue_window),
                            vo_sec=float(dur),
                            plan=plan,
                            sample_rate=SR,
                        )
                        wav = fitted_cue
                        dur = float(cue_window)
                        log(
                            f"  vo_atempo→cue_window factor={plan.get('atempo')} "
                            f"raw→{cue_window:.2f}s"
                        )
                    except VoAtempoError as exc:
                        raise RenderError(
                            f"{sid} voice cue exceeds reserved window "
                            f"({dur:.2f}s > {cue_window:.2f}s); atempo failed: {exc}"
                        ) from exc
                else:
                    raise RenderError(
                        f"{sid} voice cue exceeds its reserved window "
                        f"({dur:.2f}s > {cue_window:.2f}s); shorten text, "
                        "use --vo-fit atempo, or enlarge audio_cues duration within slot"
                    )
        # shorter tail — snappier cut to next shot
        # non-vo coverage / native XOR: silence already matches plate; no VO pad stretch
        if non_vo_coverage or dialogue_audio_lane in {"native", "silence"}:
            pad = 0.0
            target = float(dur)
        else:
            pad = float(getattr(args, "vo_pad", 0.12) or 0.12)
            target = dur + pad
        # visual_fit: "slot" locks to duration_sec; "vo" follows VO length.
        # Wave γ · dialogue_drama / spoken / mid_motion → vo (anti equal-length PPT).
        # See lessons-2026-07-20-action-fluency.md · shortform_no_double_play.
        # Native dialogue lane: always plate/slot (Edge is caption-only, not duration owner).
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
        if dialogue_audio_lane == "native":
            use_fit = "slot"
        visual_fit = str(spec.get("visual_fit") or default_fit).strip().lower()
        slot = resolve_plate_slot_sec(shot, default=0.0, min_sec=0.0)
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
            in_point = coerce_optional_float(shot.get("in_point_sec"))
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
                # XOR: post_tts suppresses native; native keeps clip audio and
                # silent Edge caption clock. Never both audible for same line.
                "dialogue_audio_lane": dialogue_audio_lane,
                "tts_mix_gain": tts_mix_gain,
                "caption_clock_only": caption_clock_only,
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

    return shot_audio
