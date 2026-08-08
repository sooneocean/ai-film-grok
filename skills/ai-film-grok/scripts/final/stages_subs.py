"""Subtitle cue clock + SRT + optional PIL burn (orchestrator relief W1.4).

Structure-only peel from render_final stage 8. Default subs=off (HF owns
visible captions); burn is explicit FFmpeg compatibility path.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from final.caption_text import build_subtitle_cues_for_shots, write_srt
from final.cards import sub_png
from final.enhance import resolve_subtitle_mode
from final.media_ops import stable_path_for_ffmpeg_filter
from logger import log
from security_policy import SecurityPolicyError, safe_output_path
from util import write_json


def build_final_cues(
    *,
    shot_audio: list[dict[str, Any]],
    title_duration: float,
    end_duration: float,
    transition_sec: float,
    sub_lead: float,
    sub_min: float,
    sub_max: float,
    story_join_intents: list[Any] | None,
    default_intent: str,
    use_event_tts: bool,
    formal_timeline: dict[str, Any] | None,
    timeline_caption_bindings: Callable[[dict[str, Any]], list[dict[str, Any]]],
    audio_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]] | None]:
    """Build subtitle cues + film timeline; optional event-TTS caption bindings."""
    cues, film_tl = build_subtitle_cues_for_shots(
        shot_audio,
        title_duration=title_duration,
        end_duration=end_duration,
        transition_sec=transition_sec,
        sub_lead=sub_lead,
        sub_min=sub_min,
        sub_max=sub_max,
        story_join_intents=list(story_join_intents) if story_join_intents is not None else None,
        default_intent=default_intent,
    )
    event_caption_bindings: list[dict[str, Any]] | None = None
    if use_event_tts and formal_timeline is not None:
        event_caption_bindings = timeline_caption_bindings(formal_timeline)
        cues = [
            {
                "start": row["start_sec"],
                "end": row["end_sec"],
                "text": row["caption_text"],
                "audio_event_id": row["audio_event_id"],
            }
            for row in event_caption_bindings
        ]
        write_json(audio_dir / "event-subtitle-bindings.json", event_caption_bindings)
    return cues, film_tl, event_caption_bindings


def write_final_srt(
    *,
    out_dir: Path,
    cues: list[dict[str, Any]],
    preserve_overlaps: bool,
    render_error_cls: type[Exception],
) -> tuple[Path, Path]:
    """Write final.srt and optional space-free mirror for ffmpeg filters."""
    try:
        srt_path = safe_output_path(
            out_dir, "final.srt", suffixes={".srt"}, field="subtitle sidecar"
        )
    except SecurityPolicyError as exc:
        raise render_error_cls(str(exc)) from exc
    write_srt(srt_path, cues, preserve_overlaps=preserve_overlaps)
    # Wave D · if film root path has spaces, also mirror SRT to /tmp for any
    # libass/subtitles= consumers (PIL burn already uses PNG overlays, no force_style).
    srt_stable = stable_path_for_ffmpeg_filter(srt_path, suffix=".srt", prefix="aifilm-srt")
    if srt_stable != srt_path:
        log(f"SRT mirrored to space-free path for ffmpeg filters: {srt_stable}")
    return srt_path, srt_stable


def burn_or_copy_subs(
    *,
    args: Any,
    silent: Path,
    work: Path,
    overlays_dir: Path,
    cues: list[dict[str, Any]],
    shot_dicts: list[dict[str, Any]],
    width: int,
    height: int,
    font_path: str,
    run: Callable[..., Any],
) -> tuple[Path, str]:
    """Copy silent plate or burn PIL subtitle overlays. Returns (video_subbed, subs_mode)."""
    # --subs off keeps SRT only (for HyperFrames designed captions underlay path).
    subs_mode = resolve_subtitle_mode(args)
    video_subbed = work / "video_subbed.mp4"
    if subs_mode == "off" or not cues:
        shutil.copy2(silent, video_subbed)
        return video_subbed, subs_mode

    overlay_inputs: list[str] = ["-i", str(silent)]
    filter_parts: list[str] = []
    last = "[0:v]"
    oidx = 1
    for i, cue in enumerate(cues):
        png = overlays_dir / f"sub_{i:03d}.png"
        shot_index = cue.get("shot_index", 0)
        shot = shot_dicts[shot_index] if shot_dicts and shot_index < len(shot_dicts) else {}
        safe_area = (shot.get("dsl") or {}).get("safe_area") or {}

        # Subtitles default to bottom, but we dodge to top if subtitle_clear is explicitly false
        dodge = safe_area.get("subtitle_clear") is False
        italic = cue.get("is_monologue", False)

        sub_png(
            cue["text"],
            png,
            width=width,
            height=height,
            font_path=font_path,
            dodge=dodge,
            italic=italic,
        )
        overlay_inputs += ["-i", str(png)]
        out_label = f"[o{i}]"
        filter_parts.append(
            f"{last}[{oidx}:v]overlay=0:0:enable='between(t,{cue['start']:.3f},{cue['end']:.3f})'{out_label}"
        )
        last = out_label
        oidx += 1
    if filter_parts:
        run(
            [
                "ffmpeg",
                "-y",
                *overlay_inputs,
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                last,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                str(video_subbed),
            ]
        )
    else:
        shutil.copy2(silent, video_subbed)
    return video_subbed, subs_mode


def materialize_subs_stage(
    *,
    args: Any,
    out_dir: Path,
    audio_dir: Path,
    work: Path,
    overlays_dir: Path,
    silent: Path,
    shot_audio: list[dict[str, Any]],
    shot_dicts: list[dict[str, Any]],
    title_duration: float,
    end_duration: float,
    active_transition: float,
    story_intents: list[Any] | None,
    default_intent: str,
    use_event_tts: bool,
    formal_timeline: dict[str, Any] | None,
    timeline_caption_bindings: Callable[[dict[str, Any]], list[dict[str, Any]]],
    width: int,
    height: int,
    font_path: str,
    run: Callable[..., Any],
    render_error_cls: type[Exception],
) -> dict[str, Any]:
    """Full stage 8: cues → SRT → burn/copy. Returns paths + mode + film_tl."""
    sub_lead = float(getattr(args, "sub_lead", 0.0) or 0.0)
    sub_min = float(getattr(args, "sub_min_unit", 0.48) or 0.48)
    sub_max = float(getattr(args, "sub_max_unit", 1.75) or 1.75)
    cues, film_tl, event_caption_bindings = build_final_cues(
        shot_audio=shot_audio,
        title_duration=title_duration,
        end_duration=end_duration,
        transition_sec=active_transition,
        sub_lead=sub_lead,
        sub_min=sub_min,
        sub_max=sub_max,
        story_join_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent if active_transition > 0 else "hard",
        use_event_tts=use_event_tts,
        formal_timeline=formal_timeline,
        timeline_caption_bindings=timeline_caption_bindings,
        audio_dir=audio_dir,
    )
    srt_path, srt_stable = write_final_srt(
        out_dir=out_dir,
        cues=cues,
        preserve_overlaps=use_event_tts,
        render_error_cls=render_error_cls,
    )
    video_subbed, subs_mode = burn_or_copy_subs(
        args=args,
        silent=silent,
        work=work,
        overlays_dir=overlays_dir,
        cues=cues,
        shot_dicts=shot_dicts,
        width=width,
        height=height,
        font_path=font_path,
        run=run,
    )
    return {
        "cues": cues,
        "film_tl": film_tl,
        "event_caption_bindings": event_caption_bindings,
        "srt_path": srt_path,
        "srt_stable": srt_stable,
        "video_subbed": video_subbed,
        "subs_mode": subs_mode,
    }
