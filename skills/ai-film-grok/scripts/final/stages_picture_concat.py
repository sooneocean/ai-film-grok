"""Picture stretch + title/end cards + join concat (orchestrator relief W1.6).

Structure-only peel of render_final stages 2–4. No dialogue/TTS policy change.
Post lipsync remains off — stretch fits silent I2V plate to VO/native clock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from edit_policy import (
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    expand_story_join_intents,
    expand_story_join_styles,
    normalize_transition_sec,
)
from final.cards import mkcard_video
from final.errors import RenderError
from final.media_ops import (
    apply_dialogue_broll_visual,
    concat_videos,
    resolve_join_transition_secs,
    stretch_clip,
)
from logger import log


def stretch_shot_plates(
    *,
    shot_audio: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    work: Path,
    width: int,
    height: int,
    fps: int,
    tts_backend: str,
    vo_mode: str,
    native_audio_volume: float,
    resume: bool,
    checkpoint: Any,
    root: Path,
    write_broll_edit_report: Callable[..., Any],
    heartbeat: Callable[[str, str | None], None] | None = None,
) -> tuple[list[Path], list[dict[str, Any]], dict[str, Any], str | None]:
    """Stretch each plate to VO/native clock; apply dialogue B-roll composites."""
    if heartbeat:
        heartbeat("stretch", f"shots={len(shot_audio)}")
    lipsync_report: list[dict[str, Any]] = []
    stretched: list[Path] = []
    shots_by_id = {shot.get("id"): shot for shot in shots}
    for i, item in enumerate(shot_audio):
        out = work / f"v_{i:02d}_{item['id']}.mp4"
        shot_meta = shots_by_id.get(item["id"], {})
        beat = shot_meta.get("dramatic_function") if isinstance(shot_meta, dict) else None
        checkpoint_contract = {
            "tts_backend": str(tts_backend),
            "vo_mode": vo_mode,
            "lipsync": "off",
            "native_audio_volume": native_audio_volume,
        }
        checkpoint_signature = checkpoint.signature(
            item["clip"],
            target=float(item["target"]),
            width=width,
            height=height,
            fps=fps,
            lipsync="off",
            in_point_sec=item.get("in_point_sec"),
            out_point_sec=item.get("out_point_sec"),
            contract=checkpoint_contract,
        )
        if resume:
            cached = checkpoint.get(item["id"], checkpoint_signature)
            if cached is not None:
                metadata = (
                    cached.get("metadata") if isinstance(cached.get("metadata"), dict) else {}
                )
                item["stretch_plan"] = metadata.get("stretch_plan")
                if metadata.get("target") is not None:
                    item["target"] = float(metadata["target"])
                cached_output = Path(str(cached["output"]))
                stretched.append(cached_output)
                log(f"resume {item['id']} -> {cached_output.name}")
                continue
        log(f"stretch {item['id']} -> {item['target']:.2f}s")
        stretch_plan = stretch_clip(
            item["clip"],
            out,
            target=item["target"],
            width=width,
            height=height,
            fps=fps,
            dramatic_function=str(beat) if beat else None,
            in_point_sec=item.get("in_point_sec"),
            out_point_sec=item.get("out_point_sec"),
        )
        item["stretch_plan"] = stretch_plan
        eff = stretch_plan.get("effective_target")
        if eff is not None:
            try:
                eff_f = float(eff)
                if eff_f > 0 and abs(eff_f - float(item["target"])) > 0.04:
                    log(
                        f"  clamp target {item['target']:.2f}s → {eff_f:.2f}s "
                        f"({stretch_plan.get('clamp_reason') or 'stretch'})"
                    )
                    item["target"] = eff_f
                    item["vo_dur"] = min(float(item.get("vo_dur") or eff_f), eff_f)
            except (TypeError, ValueError):
                pass
        log(
            f"  stretch mode={stretch_plan.get('mode')} loops={stretch_plan.get('loops')} "
            f"freeze={stretch_plan.get('freeze_sec')}"
        )
        stretched.append(out)
        checkpoint.mark_done(
            item["id"],
            signature=checkpoint_signature,
            output=out,
            metadata={
                "target": item["target"],
                "checkpoint_contract": checkpoint_contract,
                "stretch_plan": item.get("stretch_plan"),
                "lipsync": None,
            },
        )

    broll_edit_entries: list[dict[str, Any]] = []
    for index, item in enumerate(shot_audio):
        entries = item.get("dialogue_broll") or []
        if not entries:
            continue
        composite, entries_report = apply_dialogue_broll_visual(
            stretched[index],
            parent_id=str(item["id"]),
            parent_duration=float(item["target"]),
            entries=entries,
            work=work,
            width=width,
            height=height,
            fps=fps,
        )
        stretched[index] = composite
        broll_edit_entries.extend(entries_report)
    broll_edit_report: dict[str, Any] = {
        "schema_version": 1,
        "audio_policy": "carry_parent_dialogue",
        "entries": [],
    }
    broll_edit_report_sha256: str | None = None
    if broll_edit_entries:
        broll_edit_report, _broll_report_path, broll_edit_report_sha256 = write_broll_edit_report(
            root, broll_edit_entries
        )
    return stretched, lipsync_report, broll_edit_report, broll_edit_report_sha256


def make_title_end_cards(
    *,
    args: Any,
    spec: dict[str, Any],
    manifest: dict[str, Any],
    work: Path,
    width: int,
    height: int,
    fps: int,
    font_path: str,
) -> dict[str, Any]:
    """Render optional title/end pad plates (blank or text)."""
    plate_cards = str(getattr(args, "plate_cards", "blank") or "blank").strip().lower()
    if plate_cards not in {"text", "blank"}:
        raise RenderError("--plate-cards must be text|blank")
    title_text = args.title or spec.get("title") or manifest.get("title") or "AI Film"
    end_text = args.end_title or "— 完 —"
    title_mp4 = work / "title.mp4"
    end_mp4 = work / "end.mp4"
    title_dur = float(args.title_dur)
    end_dur = float(args.end_dur)
    title_draw = "" if plate_cards == "blank" else str(title_text)
    end_draw = "" if plate_cards == "blank" else str(end_text)
    if title_dur > 0.01:
        mkcard_video(
            title_draw,
            title_mp4,
            width=width,
            height=height,
            duration=title_dur,
            fps=fps,
            font_path=font_path,
        )
    if end_dur > 0.01:
        mkcard_video(
            end_draw,
            end_mp4,
            width=width,
            height=height,
            duration=end_dur,
            fps=fps,
            font_path=font_path,
        )
    return {
        "title_text": title_text,
        "end_text": end_text,
        "title_mp4": title_mp4,
        "end_mp4": end_mp4,
        "title_dur": title_dur,
        "end_dur": end_dur,
        "plate_cards": plate_cards,
    }


def concat_picture_timeline(
    *,
    shot_audio: list[dict[str, Any]],
    stretched: list[Path],
    work: Path,
    args: Any,
    spec: dict[str, Any],
    title_mp4: Path,
    end_mp4: Path,
    title_dur: float,
    end_dur: float,
    fps: int,
    heartbeat: Callable[[str, str | None], None] | None = None,
) -> dict[str, Any]:
    """Join title + shots + end into silent picture track with per-join intents/styles."""
    try:
        transition_sec = normalize_transition_sec(
            getattr(args, "transition_sec", None)
            if getattr(args, "transition_sec", None) is not None
            else spec.get("transition_sec", DEFAULT_TRANSITION_SEC)
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    story_intents = spec.get("transition_intents")
    if story_intents is not None and not isinstance(story_intents, list):
        raise RenderError("film-spec transition_intents must be an array")
    default_intent = str(spec.get("transition_default") or "soft")
    try:
        full_join_intents = expand_story_join_intents(
            len(shot_audio),
            story_intents=list(story_intents) if story_intents is not None else None,
            default_intent=default_intent if transition_sec > 0 else "hard",
            edge_intent=default_intent if transition_sec > 0 else "hard",
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    parts: list[Path] = []
    if title_dur > 0.01:
        parts.append(title_mp4)
    parts.extend(stretched)
    if end_dur > 0.01:
        parts.append(end_mp4)
    silent = work / "video_silent.mp4"
    transition_style = str(spec.get("transition_style") or "fade").strip().lower() or "fade"
    story_styles = spec.get("transition_styles")
    if story_styles is not None and not isinstance(story_styles, list):
        raise RenderError("film-spec transition_styles must be an array")
    try:
        full_join_styles = expand_story_join_styles(
            len(shot_audio),
            story_styles=[str(x) for x in story_styles] if story_styles is not None else None,
            edge_style=transition_style,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    ops_for_align = spec.get("transition_ops")
    if isinstance(ops_for_align, list) and ops_for_align and len(full_join_styles) >= 2:
        try:
            try:
                from plan.plate_transition_align import (
                    align_story_styles_to_transition_ops,
                    plate_transition_ops_alignment_report,
                )
            except ImportError:  # pragma: no cover
                from plate_transition_align import (  # type: ignore
                    align_story_styles_to_transition_ops,
                    plate_transition_ops_alignment_report,
                )

            between = list(full_join_styles[1:-1])
            align_rep = plate_transition_ops_alignment_report(
                transition_ops=ops_for_align,
                story_styles=between
                if between
                else [str(x) for x in (story_styles or [])],
                story_intents=(
                    list(story_intents) if isinstance(story_intents, list) else None
                ),
            )
            if not align_rep.get("ok"):
                soft_t = bool(spec.get("transition_policy_soft") is True)
                if not soft_t:
                    msg = "; ".join(
                        f"[{i.get('code')}] {i.get('message')}"
                        for i in (align_rep.get("issues") or [])[:4]
                        if i.get("code") in (align_rep.get("hard_codes") or [])
                    )
                    raise RenderError(
                        f"plate transition_ops alignment: {msg or align_rep.get('hard_codes')}"
                    )
            if between:
                aligned, _iss = align_story_styles_to_transition_ops(ops_for_align, between)
                full_join_styles = [full_join_styles[0], *aligned, full_join_styles[-1]]
        except RenderError:
            raise
        except Exception as exc:  # noqa: BLE001
            log(f"plate transition_ops align skipped: {exc}"[:160])
    full_join_use_ts = resolve_join_transition_secs(
        spec.get("join_transition_secs"),
        n_parts=len(parts),
        n_shots=len(shot_audio),
        transition_sec=transition_sec,
    )
    if heartbeat:
        heartbeat("video_concat", f"parts={len(parts)}")
    xfade_plan = concat_videos(
        parts,
        silent,
        transition_sec=transition_sec,
        fps=fps,
        join_intents=full_join_intents,
        transition_style=transition_style,
        join_styles=full_join_styles,
        join_use_ts=full_join_use_ts,
    )
    log(
        f"video concat method={xfade_plan.get('method')} transition_sec={transition_sec} "
        f"style={transition_style} styles={xfade_plan.get('join_styles')} "
        f"join_use_ts={full_join_use_ts} "
        f"enabled={xfade_plan.get('enabled')} joins={full_join_intents}"
    )
    return {
        "silent": silent,
        "parts": parts,
        "transition_sec": transition_sec,
        "story_intents": story_intents,
        "default_intent": default_intent,
        "full_join_intents": full_join_intents,
        "full_join_styles": full_join_styles,
        "full_join_use_ts": full_join_use_ts,
        "transition_style": transition_style,
        "xfade_plan": xfade_plan,
    }


def assemble_picture_track(
    *,
    shot_audio: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    work: Path,
    width: int,
    height: int,
    fps: int,
    tts_backend: str,
    vo_mode: str,
    native_audio_volume: float,
    resume: bool,
    checkpoint: Any,
    root: Path,
    args: Any,
    spec: dict[str, Any],
    manifest: dict[str, Any],
    font_path: str,
    write_broll_edit_report: Callable[..., Any],
    heartbeat: Callable[[str, str | None], None] | None = None,
) -> dict[str, Any]:
    """Stages 2–4: stretch → title/end → concat."""
    stretched, lipsync_report, broll_edit_report, broll_sha = stretch_shot_plates(
        shot_audio=shot_audio,
        shots=shots,
        work=work,
        width=width,
        height=height,
        fps=fps,
        tts_backend=tts_backend,
        vo_mode=vo_mode,
        native_audio_volume=native_audio_volume,
        resume=resume,
        checkpoint=checkpoint,
        root=root,
        write_broll_edit_report=write_broll_edit_report,
        heartbeat=heartbeat,
    )
    cards = make_title_end_cards(
        args=args,
        spec=spec,
        manifest=manifest,
        work=work,
        width=width,
        height=height,
        fps=fps,
        font_path=font_path,
    )
    concat = concat_picture_timeline(
        shot_audio=shot_audio,
        stretched=stretched,
        work=work,
        args=args,
        spec=spec,
        title_mp4=cards["title_mp4"],
        end_mp4=cards["end_mp4"],
        title_dur=cards["title_dur"],
        end_dur=cards["end_dur"],
        fps=fps,
        heartbeat=heartbeat,
    )
    return {
        "stretched": stretched,
        "lipsync_report": lipsync_report,
        "broll_edit_report": broll_edit_report,
        "broll_edit_report_sha256": broll_sha,
        **cards,
        **concat,
    }
