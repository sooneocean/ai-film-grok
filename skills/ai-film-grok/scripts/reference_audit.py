"""Reference-video audit: reverse-engineer shot grammar from a reference clip.

Given a reference video (product film, cinematic clip, competitor launch
video), this module produces:

  * ``probe.json`` — format/streams/duration/bitrate
  * ``contact-sheet.jpg`` — full-video thumbnail grid with timestamp overlays
  * ``keyframes/t<N>.png`` — extracted frames at requested timestamps
  * ``volume.txt`` / ``silence.txt`` — audio reality (speech vs music vs silent)
  * ``shot-grammar.json`` — structured summary: duration, aspect ratio, audio
    reality, shot count estimate, suggested visual grammar and palette hints.

The shot-grammar summary is designed to feed ``cinema_prompt.inject_camera_prompts``
indirectly — an agent reads the grammar and maps its ``suggested_dsl_overrides``
onto the film-spec shots before injection.

Inspired by the reference-driven-cinematic-video ``analyze_reference_video.py``,
adapted to use ``media_probe`` / ``security_policy`` infrastructure.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from media_probe import DEFAULT_DECODE_TIMEOUT, run_media_command
from util import write_json

# Aspect-ratio classification buckets.
ASPECT_9_16 = (9, 16)
ASPECT_16_9 = (16, 9)
ASPECT_1_1 = (1, 1)


class ReferenceAuditError(RuntimeError):
    """The reference video could not be analysed."""


def _aspect_ratio(width: int, height: int) -> tuple[int, int] | None:
    if not width or not height:
        return None
    from math import gcd

    g = gcd(width, height)
    return (width // g, height // g)


def _classify_aspect(ar: tuple[int, int] | None) -> str:
    if ar is None:
        return "unknown"
    if ar == ASPECT_9_16 or ar[0] / ar[1] < 0.62:
        return "vertical"
    if ar == ASPECT_16_9 or ar[0] / ar[1] > 1.5:
        return "horizontal"
    if ar == ASPECT_1_1 or 0.9 < ar[0] / ar[1] < 1.1:
        return "square"
    return "custom"


def _parse_db(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else None


def _audio_reality(volume_stderr: str, silence_stderr: str) -> dict[str, Any]:
    """Classify whether the reference has speech, music, or is silent."""
    mean = _parse_db(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", volume_stderr)
    max_vol = _parse_db(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", volume_stderr)
    has_silence = "silence_start:" in silence_stderr
    if mean is not None and mean < -50:
        kind = "silent"
    elif has_silence and mean is not None and mean < -25:
        kind = "music_only"
    else:
        kind = "speech"
    return {
        "kind": kind,
        "mean_volume_db": mean,
        "max_volume_db": max_vol,
        "has_silence_intervals": has_silence,
    }


def _estimate_shot_count(duration: float, silence_stderr: str) -> int:
    """Rough shot-count estimate from silence boundaries (cuts often align with audio gaps)."""
    if duration <= 0:
        return 0
    # Count silence_start markers as potential cut points.
    cuts = silence_stderr.count("silence_start:")
    # Fall back to one shot per ~4 seconds if no silence detected.
    estimated = max(cuts, int(duration / 4.0))
    return min(max(estimated, 3), 30)  # clamp to [3, 30]


def _build_contact_sheet(path: Path, out: Path, *, duration: float) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    cols, rows = 5, 3
    step = max(duration / (cols * rows), 0.5) if duration else 4.0
    vf = (
        f"fps=1/{step:.3f},scale=320:-1,"
        "drawtext=text='%{pts\\:hms}':x=8:y=8:fontsize=18:"
        "fontcolor=white:box=1:boxcolor=black@0.55,"
        f"tile={cols}x{rows}:padding=8:margin=8:color=black"
    )
    process = run_media_command(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-update",
            "1",
            str(out),
            "-y",
        ],
        timeout=DEFAULT_DECODE_TIMEOUT,
        check=False,
    )
    if process.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        vf_simple = (
            f"fps=1/{step:.3f},scale=320:-1,tile={cols}x{rows}:padding=8:margin=8:color=black"
        )
        process = run_media_command(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-vf",
                vf_simple,
                "-frames:v",
                "1",
                "-update",
                "1",
                str(out),
                "-y",
            ],
            timeout=DEFAULT_DECODE_TIMEOUT,
            check=False,
        )
    return out.is_file() and out.stat().st_size > 0


def _extract_keyframes(path: Path, kf_dir: Path, frames_csv: str) -> list[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    extracted: list[str] = []
    for raw_time in frames_csv.split(","):
        ts = raw_time.strip()
        if not ts:
            continue
        safe = ts.replace(".", "_")
        out_path = kf_dir / f"t{safe}.png"
        run_media_command(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-ss",
                ts,
                "-i",
                str(path),
                "-frames:v",
                "1",
                str(out_path),
                "-y",
            ],
            timeout=DEFAULT_DECODE_TIMEOUT,
            check=False,
        )
        if out_path.is_file():
            extracted.append(str(out_path))
    return extracted


def _build_shot_grammar(
    probe_data: dict[str, Any],
    audio: dict[str, Any],
    shot_count: int,
    keyframes: list[str],
) -> dict[str, Any]:
    """Compose the structured shot-grammar summary for cinema_prompt mapping."""
    streams = probe_data.get("streams") or []
    video_stream = next(
        (s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), {}
    )
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    fps_raw = str(video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate") or "0/1")
    duration = float(probe_data.get("format", {}).get("duration") or 0.0)
    ar = _aspect_ratio(width, height)
    aspect_class = _classify_aspect(ar)

    # Suggest a visual grammar carrier based on aspect ratio + audio.
    if aspect_class == "vertical":
        carrier = "vertical_drama"
    elif aspect_class == "horizontal" and audio["kind"] == "speech":
        carrier = "editorial_narration"
    elif aspect_class == "horizontal":
        carrier = "cinematic_widescreen"
    else:
        carrier = "general"

    # Palette hints from aspect + audio mood.
    palette_hints: list[str] = []
    if audio["kind"] == "silent":
        palette_hints = ["neutral_dark", "single_accent"]
    elif audio["kind"] == "music_only":
        palette_hints = ["warm_neutral", "dual_tone"]
    else:
        palette_hints = ["editorial_contrast", "skin_tone_protection"]

    return {
        "schema_version": 1,
        "kind": "reference-shot-grammar",
        "duration_sec": round(duration, 2),
        "dimensions": {"width": width, "height": height},
        "aspect_ratio": f"{ar[0]}:{ar[1]}" if ar else None,
        "aspect_class": aspect_class,
        "frame_rate_raw": fps_raw,
        "audio_reality": audio,
        "estimated_shot_count": shot_count,
        "suggested_visual_carrier": carrier,
        "suggested_palette_hints": palette_hints,
        "keyframe_count": len(keyframes),
        "keyframes": keyframes,
        # DSL override hints — an agent maps these onto film-spec shots
        # before calling cinema_prompt.inject_camera_prompts.
        "suggested_dsl_overrides": {
            "camera_axis": "static" if shot_count <= 4 else "dynamic",
            "pacing": "slow" if shot_count <= 4 else "medium",
            "palette": palette_hints[0] if palette_hints else None,
        },
        "note": (
            "Auto-derived from FFmpeg probe only. An agent should review the "
            "contact sheet and keyframes, then refine suggested_dsl_overrides "
            "before injecting into film-spec shots."
        ),
    }


def run_reference_audit(
    video: Path | str,
    *,
    out_dir: Path | str | None = None,
    frames: str = "0,3,6,9,13,18,24,30,36",
) -> dict[str, Any]:
    """Analyse a reference video and produce shot-grammar + artefacts.

    Returns the ``shot-grammar.json`` summary dict.
    """
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise ReferenceAuditError(f"reference video not found: {video}")

    out = (
        Path(out_dir).expanduser().resolve()
        if out_dir
        else video.with_suffix("").parent / "reference-analysis"
    )
    out.mkdir(parents=True, exist_ok=True)
    keyframes_dir = out / "keyframes"
    keyframes_dir.mkdir(exist_ok=True)

    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise ReferenceAuditError("ffmpeg/ffprobe required for reference audit")

    # Probe
    entries = (
        "format=duration,size,bit_rate:stream=index,codec_name,codec_type,"
        "width,height,r_frame_rate,avg_frame_rate,duration,channels"
    )
    probe_proc = run_media_command(
        [ffprobe, "-v", "error", "-show_entries", entries, "-of", "json", str(video)],
        timeout=DEFAULT_DECODE_TIMEOUT,
        check=True,
    )
    probe_data = json.loads(probe_proc.stdout)
    (out / "probe.json").write_text(
        json.dumps(probe_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Audio reality (volumedetect via single core.media_ops path)
    from core.media_ops import probe_volume_stats

    volume_stats = probe_volume_stats(
        video, strip_video=True, timeout=float(DEFAULT_DECODE_TIMEOUT)
    )
    volume_stderr = str(volume_stats.get("raw_text") or "")
    silence_proc = run_media_command(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-af",
            "silencedetect=noise=-50dB:d=0.5",
            "-vn",
            "-f",
            "null",
            "-",
        ],
        timeout=DEFAULT_DECODE_TIMEOUT,
        check=False,
    )
    silence_stderr = (silence_proc.stderr or "").strip()
    (out / "volume.txt").write_text(volume_stderr, encoding="utf-8")
    (out / "silence.txt").write_text(silence_stderr, encoding="utf-8")

    duration = float(probe_data.get("format", {}).get("duration") or 0.0)
    audio = _audio_reality(volume_stderr, silence_stderr)
    shot_count = _estimate_shot_count(duration, silence_stderr)

    # Contact sheet
    contact_sheet = out / "contact-sheet.jpg"
    _build_contact_sheet(video, contact_sheet, duration=duration)

    # Keyframes
    keyframes = _extract_keyframes(video, keyframes_dir, frames)

    # Shot grammar summary
    grammar = _build_shot_grammar(probe_data, audio, shot_count, keyframes)
    grammar["reference_video"] = str(video)
    grammar["out_dir"] = str(out)
    grammar["probe"] = str(out / "probe.json")
    grammar["volume"] = str(out / "volume.txt")
    grammar["silence"] = str(out / "silence.txt")
    grammar["contact_sheet"] = str(contact_sheet) if contact_sheet.is_file() else None

    write_json(out / "shot-grammar.json", grammar)
    return grammar
