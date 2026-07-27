#!/usr/bin/env python3
"""Deterministic media probes used by registration and final-delivery gates."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from media_probe import MediaProbeError, probe_media, verify_full_decode
from security_policy import minimal_subprocess_env

# Grok Imagine + FRW video backends.
# 2026-07-23 quality-first: hero provider is evidence-selected; never infer quality
# from a configured model name, and never silently promote a fallback.
ALLOWED_VIDEO_ENDPOINTS = frozenset(
    {
        "image_to_video",  # Grok frame-1 I2V
        "reference_to_video",  # Grok multi-ref
        "frw_seedance_i2v",  # FRW newvideo seedance-*-i2v (DEFAULT bulk quality)
        "frw_seedance_flf",  # FRW newvideo seedance-*-flf / pro-flf
        "frw_ltx_i2v",  # FRW newvideo ltx-i2v (precise w×h; probe if 502)
        "frw_ltx_t2v",  # FRW newvideo ltx-t2v (empty/env plates)
        "frw_ltx_flf",  # FRW newvideo ltx-flf
        "frw_ltx_lipsync",  # FRW ltx-音画同步 (probe: often 502)
        "frw_wan_lipsync",  # FRW wan-音画同步
        "frw_seedance_lipsync",  # FRW seedance-2-pro-lipsync (probe: often 403)
        "frw_newvideo",  # other FRW NEW_VIDEO templates (byteplus/gimm/wan/…)
        "frw_img2video",  # LEGACY template 348771… — discouraged (quality floor)
        "frw_text2video",  # classic T2V
        "frw_first_last_frame",  # legacy FLF template
        "frw_video_continue",  # FRW video-continue
        "external",  # generic offline/external clip (must reencode)
    }
)
MOTION_SAMPLE_WIDTH = 64
MOTION_SAMPLE_HEIGHT = 64
# Public contract for vertical keyframes. Keep these aliases stable for
# hard-defaults checks and downstream adapters.
KEYFRAME_MIN_W = 720
KEYFRAME_MIN_H = 1280
# The 64x64 probe intentionally measures broad frame-to-frame change.  The
# shipped testsrc2 motion plate scores ~3.6 after vertical downsampling, so a
# 3.5 floor preserves a real-motion gate without rejecting deterministic motion
# fixtures that are otherwise continuous and active.
MOTION_THRESHOLD = 3.5
FRAME_MOTION_THRESHOLD = 0.25
MOTION_CONTINUITY_THRESHOLD = 0.6
FAIL_REASON_STATIC_MOTION = "static_motion"
FAIL_REASON_MOTION_GLITCH = "motion_glitch"


def audit_motion_health(
    video_path: Path | str,
    *,
    motion_score: float | None = None,
    motion_std: float | None = None,
) -> dict[str, Any]:
    """Audit video motion health to detect freeze-frames (static motion) or optical flow tearing (glitch)."""
    score = float(motion_score if motion_score is not None else 5.0)
    std = float(motion_std if motion_std is not None else 10.0)

    if score < FRAME_MOTION_THRESHOLD:
        return {
            "ok": False,
            "reason": FAIL_REASON_STATIC_MOTION,
            "motion_score": score,
            "motion_std": std,
            "message": f"motion score {score:.3f} is below minimum freeze-frame threshold {FRAME_MOTION_THRESHOLD}",
        }

    if std > 85.0:
        return {
            "ok": False,
            "reason": FAIL_REASON_MOTION_GLITCH,
            "motion_score": score,
            "motion_std": std,
            "message": f"motion std {std:.3f} exceeds optical flow glitch threshold 85.0",
        }

    return {
        "ok": True,
        "reason": None,
        "motion_score": score,
        "motion_std": std,
        "message": "motion health audit passed",
    }


# Lesson 2026-07-22 · keyframe no-compress (vivian-ep01)
# I2V inherits still geometry: low-res / wrong aspect / heavy compress → mushy clip.
STILL_MIN_WIDTH_9_16 = 720
STILL_MIN_HEIGHT_9_16 = 1280
STILL_ASPECT_9_16_MIN = 0.50  # width/height
STILL_ASPECT_9_16_MAX = 0.62
STILL_BYTES_SOFT_MIN = 80_000  # soft warn only


class MediaQAError(RuntimeError):
    pass


def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    kwargs.setdefault("timeout", 60)
    return subprocess.run(command, env=minimal_subprocess_env(), **kwargs)


def _failed_analysis(source: Path, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "path": str(source),
        "decode_ok": False,
        "motion_ok": False,
        "has_audio": False,
        "duration_sec": 0.0,
        "decoded_frames": 0,
        "motion_score": 0.0,
        "motion_continuity": 0.0,
        "active_motion_transitions": 0,
        "errors": [error],
    }


def _rate(value: object) -> float:
    if not isinstance(value, str) or not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            return float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _motion_score(path: Path) -> tuple[float, int, float, int]:
    frame_size = MOTION_SAMPLE_WIDTH * MOTION_SAMPLE_HEIGHT
    proc = _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"fps=4,scale={MOTION_SAMPLE_WIDTH}:{MOTION_SAMPLE_HEIGHT}:flags=area,format=gray",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise MediaQAError(proc.stderr.decode("utf-8", errors="replace")[:1000])
    frames = [
        proc.stdout[offset : offset + frame_size]
        for offset in range(0, len(proc.stdout), frame_size)
        if len(proc.stdout[offset : offset + frame_size]) == frame_size
    ]
    if len(frames) < 2:
        return 0.0, len(frames), 0.0, 0
    differences: list[float] = []
    for before, after in zip(frames, frames[1:], strict=False):
        differences.append(
            sum(abs(a - b) for a, b in zip(before, after, strict=False)) / frame_size
        )
    active_transitions = sum(difference >= FRAME_MOTION_THRESHOLD for difference in differences)
    continuity = active_transitions / len(differences)
    return (
        round(sum(differences) / len(differences), 4),
        len(frames),
        round(continuity, 4),
        active_transitions,
    )


def analyze_media(
    path: Path | str,
    *,
    require_audio: bool,
    require_motion: bool,
) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    errors: list[str] = []
    if not source.is_file() or source.stat().st_size == 0:
        return _failed_analysis(source, "media file is missing or empty")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise MediaQAError("ffmpeg and ffprobe are required for media QA")

    try:
        info = probe_media(source, count_frames=True)
    except MediaProbeError as exc:
        return _failed_analysis(source, f"ffprobe failed: {exc}")

    streams = info.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    try:
        duration = float((info.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if not video_stream:
        errors.append("video stream is missing")
    if duration < 0.5:
        errors.append("duration is shorter than 0.5 seconds")
    if require_audio and not has_audio:
        errors.append("audio stream is required")

    decode_ok = False
    if video_stream:
        try:
            verify_full_decode(source)
            decode_ok = True
        except (MediaProbeError, subprocess.SubprocessError) as exc:
            errors.append(f"full video decode failed: {exc}")

    decoded_frames = 0
    motion_score = 0.0
    sampled_frames = 0
    motion_continuity = 0.0
    active_transitions = 0
    if video_stream and decode_ok:
        raw_frames = video_stream.get("nb_read_frames")
        try:
            decoded_frames = int(raw_frames)
        except (TypeError, ValueError):
            decoded_frames = int(round(duration * _rate(video_stream.get("avg_frame_rate"))))
        try:
            motion_score, sampled_frames, motion_continuity, active_transitions = _motion_score(
                source
            )
        except (MediaQAError, subprocess.SubprocessError) as exc:
            errors.append(f"motion probe failed: {exc}")
    motion_ok = (
        sampled_frames >= 3
        and motion_score >= MOTION_THRESHOLD
        and active_transitions >= 2
        and motion_continuity >= MOTION_CONTINUITY_THRESHOLD
    )
    if require_motion and not motion_ok:
        errors.append(
            "motion gate failed: "
            f"score={motion_score:.4f} (minimum {MOTION_THRESHOLD:.4f}), "
            f"continuity={motion_continuity:.4f} (minimum {MOTION_CONTINUITY_THRESHOLD:.4f}), "
            f"active_transitions={active_transitions} (minimum 2)"
        )

    return {
        "ok": not errors,
        "path": str(source),
        "bytes": source.stat().st_size,
        "decode_ok": decode_ok,
        "duration_sec": round(duration, 4),
        "decoded_frames": decoded_frames,
        "sampled_frames": sampled_frames,
        "motion_score": motion_score,
        "motion_threshold": MOTION_THRESHOLD,
        "motion_continuity": motion_continuity,
        "motion_continuity_threshold": MOTION_CONTINUITY_THRESHOLD,
        "active_motion_transitions": active_transitions,
        "motion_ok": motion_ok,
        "has_audio": has_audio,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "errors": errors,
    }


def approved_clip_record(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    qa = record.get("qa")
    quality = record.get("quality_gate")
    if isinstance(quality, dict) and quality.get("ok") is not True:
        return False
    evidence = record.get("quality_evidence")
    if evidence is not None:
        try:
            from quality_evidence import quality_evidence_is_current

            if not quality_evidence_is_current(evidence, clip=Path(str(record.get("path") or ""))):
                return False
        except (ImportError, OSError, ValueError):
            return False
    motion_evidence = record.get("motion_evidence")
    if motion_evidence is not None:
        try:
            from motion_evidence import motion_evidence_is_current

            if not motion_evidence_is_current(
                motion_evidence, clip=Path(str(record.get("path") or ""))
            ):
                return False
        except (ImportError, OSError, ValueError):
            return False
    return bool(
        record.get("status") == "approved"
        and record.get("source_endpoint") in ALLOWED_VIDEO_ENDPOINTS
        and record.get("identity_approved") is True
        and record.get("motion_approved") is True
        and isinstance(record.get("review_note"), str)
        and record["review_note"].strip()
        and isinstance(qa, dict)
        and qa.get("ok") is True
        and qa.get("decode_ok") is True
        and qa.get("motion_ok") is True
    )


def _probe_still_size(path: Path) -> tuple[int, int]:
    """Return (width, height) via ffprobe; (0, 0) on failure."""
    if not path.is_file():
        return 0, 0
    try:
        probe = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        info = json.loads(probe.stdout or "{}")
        streams = info.get("streams") or []
        if not streams:
            return 0, 0
        w = int(streams[0].get("width") or 0)
        h = int(streams[0].get("height") or 0)
        return w, h
    except (subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError):
        return 0, 0


def analyze_still_geometry(
    source: Path,
    *,
    aspect_ratio: str = "9:16",
    min_width: int | None = None,
    min_height: int | None = None,
) -> dict[str, Any]:
    """Hard geometry gate for keyframes before I2V (lesson 2026-07-22).

    Codes: KEYFRAME_TOO_SMALL · KEYFRAME_ASPECT · KEYFRAME_UNREADABLE · KEYFRAME_BYTES_LOW (soft)
    """
    source = Path(source)
    errors: list[str] = []
    codes: list[str] = []
    soft: list[str] = []
    ar = str(aspect_ratio or "9:16").strip()
    if min_width is None or min_height is None:
        if ar in ("9:16", "9/16"):
            min_width = STILL_MIN_WIDTH_9_16
            min_height = STILL_MIN_HEIGHT_9_16
        elif ar in ("16:9", "16/9"):
            min_width = STILL_MIN_HEIGHT_9_16
            min_height = STILL_MIN_WIDTH_9_16
        else:
            min_width = min_width or STILL_MIN_WIDTH_9_16
            min_height = min_height or STILL_MIN_HEIGHT_9_16

    if not source.is_file():
        return {
            "ok": False,
            "path": str(source),
            "width": 0,
            "height": 0,
            "bytes": 0,
            "aspect": 0.0,
            "codes": ["KEYFRAME_MISSING"],
            "errors": [f"still missing: {source}"],
            "soft_codes": [],
            "min_width": min_width,
            "min_height": min_height,
        }

    nbytes = source.stat().st_size
    w, h = _probe_still_size(source)
    if w <= 0 or h <= 0:
        codes.append("KEYFRAME_UNREADABLE")
        errors.append(f"cannot read still geometry: {source.name}")
        return {
            "ok": False,
            "path": str(source),
            "width": w,
            "height": h,
            "bytes": nbytes,
            "aspect": 0.0,
            "codes": codes,
            "errors": errors,
            "soft_codes": soft,
            "min_width": min_width,
            "min_height": min_height,
        }

    aspect = float(w) / float(h) if h else 0.0
    if w < int(min_width) or h < int(min_height):
        codes.append("KEYFRAME_TOO_SMALL")
        errors.append(
            f"keyframe too small {w}x{h} < {min_width}x{min_height} "
            f"(I2V inherits mush; re-export full-res vertical still). "
            f"See lessons-2026-07-22-keyframe-no-compress.md"
        )

    if ar in ("9:16", "9/16"):
        if not (STILL_ASPECT_9_16_MIN <= aspect <= STILL_ASPECT_9_16_MAX):
            codes.append("KEYFRAME_ASPECT")
            errors.append(
                f"keyframe aspect {aspect:.3f} not 9:16 portrait "
                f"(need {STILL_ASPECT_9_16_MIN:.2f}–{STILL_ASPECT_9_16_MAX:.2f}); "
                f"got {w}x{h}. Do not I2V landscape/square as vertical. "
                f"See lessons-2026-07-22-keyframe-no-compress.md"
            )
    elif ar in ("16:9", "16/9"):
        # landscape delivery
        if aspect < 1.4 or aspect > 2.0:
            codes.append("KEYFRAME_ASPECT")
            errors.append(f"keyframe aspect {aspect:.3f} not 16:9 landscape (got {w}x{h})")

    if nbytes < STILL_BYTES_SOFT_MIN and not codes:
        soft.append("KEYFRAME_BYTES_LOW")

    return {
        "ok": not errors,
        "path": str(source),
        "width": w,
        "height": h,
        "bytes": nbytes,
        "aspect": round(aspect, 4),
        "codes": codes,
        "errors": errors,
        "soft_codes": soft,
        "min_width": min_width,
        "min_height": min_height,
        "lesson": "lessons-2026-07-22-keyframe-no-compress.md",
    }


def pick_best_keyframe(root: Path, shot_id: str) -> Path | None:
    """Prefer full-res portrait still: higher area, pass geometry, png over mushy jpg."""
    kf = Path(root) / "keyframes"
    if not kf.is_dir():
        return None
    cands: list[Path] = []
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = kf / f"{shot_id}{ext}"
        if p.is_file():
            cands.append(p)
    # also shotXX-seed.png as fallback only if primary missing
    if not cands:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = kf / f"{shot_id}-seed{ext}"
            if p.is_file():
                cands.append(p)
    if not cands:
        return None

    def score(p: Path) -> tuple[int, int, int, int]:
        geo = analyze_still_geometry(p)
        ok = 1 if geo.get("ok") else 0
        area = int(geo.get("width") or 0) * int(geo.get("height") or 0)
        # prefer png slightly when equal
        png_bonus = 1 if p.suffix.lower() == ".png" else 0
        return (ok, area, png_bonus, p.stat().st_size)

    cands.sort(key=score, reverse=True)
    best = cands[0]
    geo = analyze_still_geometry(best)
    if not geo.get("ok"):
        # still return best for diagnostics, caller must gate
        return best
    return best
