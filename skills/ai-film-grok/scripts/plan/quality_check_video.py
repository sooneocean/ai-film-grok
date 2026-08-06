"""Delivery-level FFmpeg quality gates with weighted scoring.

This module sits *before* the director's subjective 11-dimension scorecard in
``review-final``.  It answers the objective question: "does the rendered file
decode cleanly, carry audio at the right loudness, and have no accidental
black/silence/freeze artefacts?"  A file that fails here is not worth a human
reviewer's time.

Inspired by the reference-driven-cinematic-video quality checker, adapted to
use the shared ``media_probe`` / ``security_policy`` infrastructure and the
ai-film-grok receipt conventions.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from media_probe import (
    DEFAULT_DECODE_TIMEOUT,
    run_media_command,
)
from security_policy import minimal_subprocess_env  # noqa: F401 (re-export for callers)
from util import read_json, write_json

# Gate weights — sum to 100.
GATE_WEIGHTS: dict[str, int] = {
    "decode": 20,
    "streams": 15,
    "audio_loudness": 15,
    "black_frames": 15,
    "subtitles": 10,
    "silence": 10,
    "freezes": 10,
    "artifacts": 5,
}

# Pass band for mean volume (dB).  Outside this → warn (not hard fail).
MEAN_VOLUME_MIN_DB = -18.0  # P3-15: unified to -16 LUFS ±2 (was -22)
MEAN_VOLUME_MAX_DB = -14.0  # P3-15: unified to -16 LUFS ±2 (was -16)
MAX_VOLUME_CEILING_DB = -1.0

# Detector thresholds (match reference-repo defaults).
SILENCE_THRESHOLD_DB = -45.0
SILENCE_MIN_DURATION = 0.8
BLACK_THRESHOLD = 0.98
BLACK_MIN_DURATION = 0.4
FREEZE_THRESHOLD_DB = -60.0
FREEZE_MIN_DURATION = 1.0


class QualityCheckError(RuntimeError):
    """The delivery quality check could not complete or failed a hard gate."""


def _gate(status: str, message: str) -> dict[str, str]:
    return {"status": status, "message": message}


def _parse_db(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else None


def _has_hit(text: str, marker: str) -> bool:
    return marker in text


def _stream_types(probe_data: dict[str, Any]) -> set[str]:
    return {
        str(stream.get("codec_type", ""))
        for stream in probe_data.get("streams") or []
        if isinstance(stream, dict)
    }


def _ffprobe_full(path: Path) -> dict[str, Any]:
    """Probe with the full entry set needed for quality scoring."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise QualityCheckError("ffprobe not found on PATH")
    entries = (
        "format=duration,size,bit_rate:stream=index,codec_name,codec_type,"
        "width,height,pix_fmt,color_range,r_frame_rate,avg_frame_rate,bit_rate,"
        "channels,channel_layout,duration"
    )
    process = run_media_command(
        [ffprobe, "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
        timeout=DEFAULT_DECODE_TIMEOUT,
        check=True,
    )
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise QualityCheckError(f"ffprobe returned invalid JSON for {path}") from exc
    return report


def _ffmpeg_decode_test(path: Path) -> str:
    """Run a full null decode; return stderr (empty on success)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise QualityCheckError("ffmpeg not found on PATH")
    process = run_media_command(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
        timeout=DEFAULT_DECODE_TIMEOUT,
        check=False,
    )
    return process.stderr.strip()


def _ffmpeg_filter(path: Path, *, filter_expr: str, audio: bool = True) -> str:
    """Run an FFmpeg detection filter and return stderr."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise QualityCheckError("ffmpeg not found on PATH")
    argv = [ffmpeg, "-hide_banner", "-nostats", "-i", str(path)]
    if audio:
        argv += ["-af", filter_expr, "-vn"]
    else:
        argv += ["-vf", filter_expr, "-an"]
    argv += ["-f", "null", "-"]
    process = run_media_command(argv, timeout=DEFAULT_DECODE_TIMEOUT, check=False)
    return process.stderr.strip()


def _build_contact_sheet(path: Path, out: Path, *, duration: float) -> bool:
    """Render a 5×3 contact sheet with timestamp overlays."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    cols, rows = 5, 3
    step = max(duration / (cols * rows), 0.5) if duration else 4.0
    vf = (
        f"fps=1/{step:.3f},scale=360:-1,"
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
        # Fallback: no drawtext (font may be missing on some systems)
        vf_simple = (
            f"fps=1/{step:.3f},scale=360:-1,tile={cols}x{rows}:padding=8:margin=8:color=black"
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


def score_gates(gates: dict[str, dict[str, str]]) -> int:
    """Compute a 0-100 weighted score from gate statuses."""
    total = 0.0
    for name, weight in GATE_WEIGHTS.items():
        status = gates.get(name, {}).get("status", "warn")
        if status == "pass":
            total += weight
        elif status == "warn":
            total += weight * 0.5
    return round(total)


def run_quality_check(
    video: Path | str,
    *,
    out_dir: Path | str | None = None,
    expect_audio: bool = True,
    expect_subtitles: bool = False,
    srt: Path | str | None = None,
    min_score: int = 0,
    allow_black: bool = False,
    allow_freeze: bool = False,
    strict_audio_loudness: bool = False,
) -> dict[str, Any]:
    """Run the full delivery-quality gate suite on one final video.

    Returns a summary dict with ``score``, ``passed``, and per-gate details.
    Writes ``quality-report.json`` + artefacts into *out_dir*.
    """
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise QualityCheckError(f"video not found: {video}")

    out = Path(out_dir).expanduser().resolve() if out_dir else video.with_suffix("")
    out.mkdir(parents=True, exist_ok=True)

    probe_data = _ffprobe_full(video)
    duration = float(probe_data.get("format", {}).get("duration") or 0.0)

    decode_errors = _ffmpeg_decode_test(video)
    from core.media_ops import probe_volume_stats

    volume_stats = probe_volume_stats(video, timeout=120.0)
    volume_stderr = str(volume_stats.get("raw_text") or "")
    silence_stderr = _ffmpeg_filter(
        video, filter_expr=f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_DURATION}"
    )
    black_stderr = _ffmpeg_filter(
        video,
        filter_expr=f"blackdetect=d={BLACK_MIN_DURATION}:pic_th={BLACK_THRESHOLD}",
        audio=False,
    )
    freeze_stderr = _ffmpeg_filter(
        video,
        filter_expr=f"freezedetect=n={FREEZE_THRESHOLD_DB}dB:d={FREEZE_MIN_DURATION}",
        audio=False,
    )

    # Persist raw detection logs
    (out / "probe.json").write_text(
        json.dumps(probe_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "decode-errors.txt").write_text(decode_errors, encoding="utf-8")
    (out / "volume.txt").write_text(volume_stderr, encoding="utf-8")
    (out / "silencedetect.txt").write_text(silence_stderr, encoding="utf-8")
    (out / "blackdetect.txt").write_text(black_stderr, encoding="utf-8")
    (out / "freezedetect.txt").write_text(freeze_stderr, encoding="utf-8")

    types = _stream_types(probe_data)
    mean_volume = volume_stats.get("mean_volume_db")
    max_volume = volume_stats.get("max_volume_db")
    if mean_volume is None:
        mean_volume = _parse_db(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", volume_stderr)
    if max_volume is None:
        max_volume = _parse_db(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", volume_stderr)

    gates: dict[str, dict[str, str]] = {}

    # 1. Decode
    gates["decode"] = (
        _gate("pass", "ffmpeg decode produced no errors")
        if not decode_errors
        else _gate("fail", "ffmpeg decode reported errors: " + decode_errors[:200])
    )

    # 2. Streams
    if "video" not in types:
        gates["streams"] = _gate("fail", "missing video stream")
    elif expect_audio and "audio" not in types:
        gates["streams"] = _gate("fail", "expected audio stream is missing")
    elif expect_audio and "audio" in types:
        gates["streams"] = _gate("pass", "video and expected audio streams present")
    else:
        gates["streams"] = _gate("pass", "video stream present")

    # 3. Audio loudness
    if "audio" not in types:
        gates["audio_loudness"] = _gate("fail" if expect_audio else "warn", "no audio stream")
    elif mean_volume is None or max_volume is None:
        gates["audio_loudness"] = _gate("warn", "could not parse volumedetect output")
    elif (
        mean_volume < MEAN_VOLUME_MIN_DB
        or mean_volume > MEAN_VOLUME_MAX_DB
        or max_volume > MAX_VOLUME_CEILING_DB
    ):
        gates["audio_loudness"] = _gate(
            "fail" if strict_audio_loudness else "warn",
            f"volume outside target (-16 LUFS ±2): mean={mean_volume} dB, max={max_volume} dB",
        )
    else:
        gates["audio_loudness"] = _gate(
            "pass",
            f"volume in target: mean={mean_volume} dB, max={max_volume} dB",
        )

    # 4. Subtitles
    srt_path = Path(srt).expanduser().resolve() if srt else None
    if expect_subtitles and srt_path and srt_path.is_file() and srt_path.stat().st_size > 0:
        gates["subtitles"] = _gate("pass", f"sidecar SRT exists: {srt_path}")
    elif expect_subtitles:
        gates["subtitles"] = _gate("fail", "expected subtitles but no non-empty SRT was provided")
    else:
        gates["subtitles"] = _gate("pass", "subtitle gate not requested")

    # 5. Black frames
    black_hit = _has_hit(black_stderr, "black_start:")
    gates["black_frames"] = (
        _gate("warn" if allow_black else "fail", "blackdetect found black interval")
        if black_hit
        else _gate("pass", "no blackdetect intervals")
    )

    # 6. Silence
    silence_hit = _has_hit(silence_stderr, "silence_start:")
    gates["silence"] = (
        _gate("warn", "silencedetect found audio silence interval")
        if silence_hit
        else _gate("pass", "no long silence intervals")
    )

    # 7. Freezes
    freeze_hit = _has_hit(freeze_stderr, "freeze_start:")
    gates["freezes"] = (
        _gate("warn" if allow_freeze else "fail", "freezedetect found frozen interval")
        if freeze_hit
        else _gate("pass", "no freezedetect intervals")
    )

    # 8. Contact sheet artefact
    contact_sheet = out / "contact-sheet.jpg"
    cs_ok = _build_contact_sheet(video, contact_sheet, duration=duration)
    gates["artifacts"] = (
        _gate("pass", f"contact sheet created: {contact_sheet}")
        if cs_ok
        else _gate("warn", "contact sheet was not created")
    )

    score = score_gates(gates)
    hard_fail = any(item["status"] == "fail" for item in gates.values())
    score_fail = min_score > 0 and score < min_score

    summary: dict[str, Any] = {
        "schema_version": 1,
        "kind": "delivery-quality",
        "video": str(video),
        "out": str(out),
        "decode_ok": gates["decode"]["status"] == "pass",
        "hard_fail": hard_fail,
        "score": score,
        "min_score": min_score,
        "passed": not hard_fail and not score_fail,
        "gates": gates,
        "metrics": {
            "duration": duration,
            "mean_volume_db": mean_volume,
            "max_volume_db": max_volume,
        },
        "contact_sheet": str(contact_sheet) if cs_ok else None,
        "probe": str(out / "probe.json"),
        "volume": str(out / "volume.txt"),
        "blackdetect": str(out / "blackdetect.txt"),
        "silencedetect": str(out / "silencedetect.txt"),
        "freezedetect": str(out / "freezedetect.txt"),
    }
    write_json(out / "quality-report.json", summary)
    return summary


def load_quality_report(root: Path | str) -> dict[str, Any] | None:
    """Read the most recent quality report from a film root's out dir."""
    report = Path(root).expanduser().resolve() / "out" / "quality-report.json"
    return read_json(report)
