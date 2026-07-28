"""Standalone SRT generator shared by all post-engines (ffmpeg / HF / Remotion).

This module is the single source of truth for SRT file generation.  Before
v1.23, ``render_final.py`` had its own ``write_srt`` and each post-engine
re-implemented subtitle writing independently — leading to the P0
"HF 失字" bug where HyperFrames failed to burn captions and no fallback
existed.

Now every post-engine calls ``write_srt_file`` or ``segments_to_srt`` so
the SRT is always written as a sidecar, independent of whether the
designed-post engine succeeds at burning captions.

Inspired by the reference-driven-cinematic-video ``srt_from_segments.py``,
which adds strict time-overlap validation that the original ``write_srt``
lacked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SrtError(ValueError):
    """SRT segment data is invalid."""


def timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp ``HH:MM:SS,mmm``."""
    millis = max(0, round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def validate_segments(
    segments: list[dict[str, Any]], *, allow_overlaps: bool = False
) -> list[dict[str, Any]]:
    """Validate a list of ``{start, end, text}`` segments for SRT correctness.

    Raises :class:`SrtError` on:
      * non-list input
      * missing keys
      * empty text
      * end <= start
      * segment starts before previous segment ends (overlap)
    """
    if not isinstance(segments, list):
        raise SrtError("segments must be a list")
    cleaned: list[dict[str, Any]] = []
    previous_end = 0.0
    for index, item in enumerate(segments, start=1):
        if not isinstance(item, dict):
            raise SrtError(f"segment {index} is not an object")
        try:
            start = float(item["start"])
            end = float(item["end"])
            text = str(item["text"]).strip()
        except KeyError as exc:
            raise SrtError(f"segment {index} missing field: {exc}") from exc
        if not text:
            raise SrtError(f"segment {index} has empty text")
        if end <= start:
            raise SrtError(f"segment {index} end must be after start")
        if not allow_overlaps and start < previous_end - 0.001:
            raise SrtError(f"segment {index} starts before previous segment ends")
        cleaned.append({"start": start, "end": end, "text": text})
        previous_end = end
    return cleaned


def segments_to_srt_text(segments: list[dict[str, Any]], *, allow_overlaps: bool = False) -> str:
    """Render validated segments into SRT subtitle text."""
    cleaned = validate_segments(segments, allow_overlaps=allow_overlaps)
    blocks: list[str] = []
    for index, cue in enumerate(cleaned, start=1):
        blocks.append(
            f"{index}\n{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n{cue['text']}"
        )
    return "\n\n".join(blocks) + "\n"


def write_srt_file(
    path: Path | str, cues: list[dict[str, Any]], *, allow_overlaps: bool = False
) -> Path:
    """Write an SRT file from a list of ``{start, end, text}`` dicts.

    This replaces the inline ``write_srt`` in ``render_final.py`` and adds
    strict overlap validation (inspired by srt_from_segments.py).

    Cues with keys ``start`` / ``end`` / ``text`` are validated: empty text,
    end<=start, and overlap are hard errors.  This catches the P0
    "字幕空窗" bug where cues were silently dropped.
    """
    # Keep the lexical path: resolving here follows a symlink and would make
    # os.replace overwrite an external target instead of replacing the link.
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Use write_json's atomic-write pattern (temp file + os.replace)
    # but write plain text, not JSON.
    import os
    import tempfile

    content = segments_to_srt_text(cues, allow_overlaps=allow_overlaps)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, target)
    return target


def write_srt_receipt(path: Path, cues: list[dict[str, Any]]) -> dict[str, Any]:
    """Write SRT + a sidecar JSON receipt with cue count and checksum."""
    from util import sha256_file

    write_srt_file(path, cues)
    return {
        "schema_version": 1,
        "kind": "srt-sidecar",
        "path": str(path),
        "cue_count": len(cues),
        "sha256": sha256_file(path) if path.is_file() else None,
    }
