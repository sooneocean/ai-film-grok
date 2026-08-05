"""FFmpeg media helpers for final assembly (peeled from render_final · W4)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from final.errors import RenderError
from runtime_policy import sha256
from edit_policy import (
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    build_acrossfade_filter_graph,
    build_xfade_filter_graph,
    normalize_transition_sec,
    plan_stretch,
)
from media_duration import MediaDurationError, probe_duration_sec
from security_policy import SecurityPolicyError, atomic_write_text, safe_existing_file, safe_output_path
from util import run_ffmpeg
from util.subprocess import run as util_run

# local wrappers used by peeled helpers
def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Subprocess runner: ffmpeg gets -nostdin + AIFILM_FFMPEG_TIMEOUT; others use the canonical 60s timeout."""
    argv = list(cmd)
    executable = Path(argv[0]).name if argv else ""
    if executable == "ffmpeg":
        return run_ffmpeg(argv, check=check)
    return util_run(cmd, check=check, timeout=60)


def pdur(path: Path | str) -> float:
    """Fail-loud duration probe — never invent silent defaults on missing media."""
    try:
        from media_duration import MediaDurationError, probe_duration_sec
    except ImportError:
        # Fallback if module missing: still fail loud on empty/missing
        p = Path(path)
        if not p.is_file():
            raise RenderError(f"media missing for duration probe: {p}") from None
        result = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ]
        )
        raw = (result.stdout or "").strip()
        if not raw:
            raise RenderError(f"unreadable duration (empty ffprobe): {path}") from None
        return float(raw)
    try:
        return probe_duration_sec(path, label="render_final")
    except MediaDurationError as exc:
        raise RenderError(str(exc)) from exc

def stretch_clip(
    src: Path,
    dest: Path,
    *,
    target: float,
    width: int,
    height: int,
    fps: int,
    dramatic_function: str | None = None,
    in_point_sec: float | None = None,
    out_point_sec: float | None = None,
) -> dict[str, Any]:
    """Fit silent I2V clip to VO length using plan_stretch.

    hook/action never stream_loop (forbid_loop). Other beats may loop when VO >> plate.
    Optional in/out points trim the plate before fit (join-handle / mid-action cut).
    Returns the stretch plan dict for logging/tests.
    """
    full_dur = pdur(src)
    if full_dur <= 0:
        raise RenderError(f"Bad source duration: {src}")
    # Join handle: use only [in, out) so match-cut lands mid-motion
    t0 = float(in_point_sec) if in_point_sec is not None and in_point_sec > 0 else 0.0
    t1 = float(out_point_sec) if out_point_sec is not None and out_point_sec > 0 else full_dur
    t0 = max(0.0, min(t0, full_dur - 0.05))
    t1 = max(t0 + 0.05, min(t1, full_dur))
    src_dur = t1 - t0
    try:
        plan = plan_stretch(src_dur, target, dramatic_function=dramatic_function)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    # P0 · 2026-07-23: shortform clamp may shrink target (anti stream_loop double-play)
    if plan.get("target_clamped") is not None:
        with contextlib.suppress(TypeError, ValueError):
            target = float(plan["target_clamped"])
    plan["in_point_sec"] = t0
    plan["out_point_sec"] = t1
    plan["source_full_dur"] = full_dur
    plan["effective_target"] = target

    base = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},format=yuv420p"
    )
    factor = float(plan["factor"])
    ss_args: list[str] = []
    if t0 > 1e-3:
        ss_args = ["-ss", f"{t0:.3f}"]

    # Trim source to [t0, t1) first via -ss/-t on input, then fit to target
    input_t_args: list[str] = []
    if t0 > 1e-3 or (out_point_sec is not None):
        input_t_args = ["-t", f"{src_dur:.3f}"]

    if plan["mode"] == "loop":
        vf = f"{base},setpts={factor:.4f}*PTS"
        run(
            [
                "ffmpeg",
                "-y",
                *ss_args,
                "-stream_loop",
                str(int(plan["loops"])),
                "-i",
                str(src),
                *input_t_args,
                "-vf",
                vf,
                "-an",
                "-t",
                f"{target:.3f}",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                str(dest),
            ]
        )
        return plan

    vf = f"{base},setpts={factor:.4f}*PTS"
    freeze = float(plan.get("freeze_sec") or 0.0)
    if freeze > 0.05:
        vf = f"{vf},tpad=stop_mode=clone:stop_duration={freeze:.3f}"
    run(
        [
            "ffmpeg",
            "-y",
            *ss_args,
            "-i",
            str(src),
            *input_t_args,
            "-vf",
            vf,
            "-an",
            "-t",
            f"{target:.3f}",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            str(dest),
        ]
    )
    return plan

def concat_videos(
    parts: list[Path],
    out: Path,
    *,
    transition_sec: float = DEFAULT_TRANSITION_SEC,
    fps: int = 30,
    join_intents: list[str] | None = None,
    transition_style: str = "fade",
    join_styles: list[str] | None = None,
    join_use_ts: list[float] | None = None,
) -> dict[str, Any]:
    """Concatenate clips with optional per-join hard/soft/hold transitions."""
    if not parts:
        raise RenderError("concat_videos: no parts")
    try:
        t_sec = normalize_transition_sec(transition_sec)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc

    durs = [pdur(p) for p in parts]
    style = (transition_style or "fade").strip().lower() or "fade"
    try:
        plan = build_xfade_filter_graph(
            durs,
            transition_sec=t_sec,
            transition=style,
            join_intents=join_intents,
            join_styles=join_styles,
            join_use_ts=join_use_ts,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc

    if not plan["enabled"]:
        lst = out.parent / "concat_final.txt"
        atomic_write_text(lst, "".join(f"file '{p.resolve()}'\n" for p in parts))
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(out),
            ]
        )
        return {**plan, "method": plan.get("method") or "hard_concat"}

    cmd: list[str] = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex",
        plan["filter_complex"],
        "-map",
        f"[{plan['output_label']}]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-an",
        str(out),
    ]
    run(cmd)
    return {**plan, "method": plan.get("method") or "xfade"}

def apply_dialogue_broll_visual(
    parent: Path,
    *,
    parent_id: str,
    parent_duration: float,
    entries: list[dict[str, Any]],
    work: Path,
    width: int,
    height: int,
    fps: int,
) -> tuple[Path, list[dict[str, Any]]]:
    """Replace bounded picture ranges while preserving the parent audio clock."""
    if not entries:
        return parent, []
    parts: list[Path] = []
    report: list[dict[str, Any]] = []
    cursor = 0.0
    for index, entry in enumerate(entries):
        start = max(cursor, float(entry["start_sec"]))
        end = min(parent_duration, float(entry["end_sec"]))
        if start - cursor > 0.02:
            prefix = work / f"{parent_id}_aroll_{index:02d}.mp4"
            stretch_clip(
                parent,
                prefix,
                target=start - cursor,
                width=width,
                height=height,
                fps=fps,
                in_point_sec=cursor,
                out_point_sec=start,
            )
            parts.append(prefix)
        cover = work / f"{parent_id}_broll_{index:02d}.mp4"
        stretch_clip(
            Path(entry["clip"]), cover, target=end - start, width=width, height=height, fps=fps
        )
        parts.append(cover)
        report.append(
            {
                "id": entry["id"],
                "parent_shot_id": parent_id,
                "source_clip": str(entry["clip"]),
                "source_sha256": sha256(Path(entry["clip"])),
                "kind": entry["kind"],
                "cut_trigger": entry["cut_trigger"],
                "narrative_purpose": entry["narrative_purpose"],
                "actual_start_sec": round(start, 3),
                "actual_end_sec": round(end, 3),
                "audio_policy": "carry_parent_dialogue",
            }
        )
        cursor = end
    if parent_duration - cursor > 0.02:
        suffix = work / f"{parent_id}_aroll_tail.mp4"
        stretch_clip(
            parent,
            suffix,
            target=parent_duration - cursor,
            width=width,
            height=height,
            fps=fps,
            in_point_sec=cursor,
            out_point_sec=parent_duration,
        )
        parts.append(suffix)
    out = work / f"{parent_id}_dialogue_broll.mp4"
    concat_videos(parts, out, transition_sec=0.0, fps=fps)
    return out, report

def concat_audio_segments(
    parts: list[Path],
    out: Path,
    *,
    transition_sec: float = DEFAULT_TRANSITION_SEC,
    segment_durs: list[float] | None = None,
    join_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Join VO (or BGM) stems with acrossfade / hard joins matching video."""
    if not parts:
        raise RenderError("concat_audio_segments: no parts")
    try:
        t_sec = normalize_transition_sec(transition_sec)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc

    durs = segment_durs
    if durs is None:
        durs = [pdur(p) for p in parts]
    if len(durs) != len(parts):
        raise RenderError("concat_audio_segments: segment_durs length mismatch")

    try:
        plan = build_acrossfade_filter_graph(
            len(parts),
            transition_sec=t_sec,
            segment_durs=durs,
            join_intents=join_intents,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    if not plan["enabled"]:
        lst = out.parent / f"{out.stem}_alist.txt"
        atomic_write_text(lst, "".join(f"file '{p.resolve()}'\n" for p in parts))
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c:a",
                "pcm_s16le",
                str(out),
            ]
        )
        return {**plan, "method": "hard_concat", "segment_durs": durs}

    cmd: list[str] = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex",
        plan["filter_complex"],
        "-map",
        f"[{plan['output_label']}]",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    run(cmd)
    return {**plan, "method": "acrossfade", "segment_durs": durs}

def stable_path_for_ffmpeg_filter(
    path: Path,
    *,
    suffix: str,
    prefix: str = "aifilm",
) -> Path:
    """Copy path to /tmp when it contains spaces (libass/subtitles= path break).

    PIL overlay burn does not need this; keep for any ``subtitles=`` / ASS consumers
    and HyperFrames handoff that pass absolute SRT paths into ffmpeg.
    """
    import tempfile

    path = Path(path).expanduser().resolve()
    text = str(path)
    if " " not in text and "\t" not in text:
        return path
    if not path.is_file():
        return path
    dest = Path(tempfile.gettempdir()) / f"{prefix}-{sha256(path)[:16]}{suffix}"
    try:
        shutil.copy2(path, dest)
    except OSError:
        return path
    return dest

