"""Mux + stream verify leaves for render_final (orchestrator relief W1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def mux_final_mp4(
    *,
    video_subbed: Path | str,
    mixed: Path | str,
    final_path: Path | str,
    run: Callable[..., Any],
) -> None:
    """Mux picture + mixed audio into final MP4 (copy video, aac audio)."""
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_subbed),
            "-i",
            str(mixed),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(final_path),
        ]
    )


def verify_final_streams(
    *,
    final_path: Path | str,
    audio_timeline_v1: bool,
    run: Callable[..., Any],
    render_error_cls: type[Exception],
) -> list[dict[str, Any]]:
    """ffprobe final MP4; require video+audio; optional 48k stereo for timeline v1."""
    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(final_path),
        ]
    )
    streams = json.loads(probe.stdout).get("streams") or []
    has_v = any(s.get("codec_type") == "video" for s in streams)
    has_a = any(s.get("codec_type") == "audio" for s in streams)
    if not has_v or not has_a:
        raise render_error_cls("Final MP4 missing video or audio stream")
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if audio_timeline_v1 and (
        not audio_stream
        or str(audio_stream.get("sample_rate")) != "48000"
        or int(audio_stream.get("channels") or 0) != 2
    ):
        raise render_error_cls("audio_timeline_v1 final must be 48kHz stereo")
    return list(streams)
