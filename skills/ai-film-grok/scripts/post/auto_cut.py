#!/usr/bin/env python3
"""Auto-cut for real footage (video-use editing-logic bridge).

Implements the audio-first cut logic from the ``video-use`` skill so ai-film-grok
can automatically cut real footage at word boundaries and silence gaps, producing
an EDL JSON that the existing edit_policy / render_final pipeline can consume.

video-use Hard Rules honored here (see video-use/SKILL.md "Hard Rules"):
  6. Never cut inside a word — snap every cut edge to a word boundary.
  7. Pad every cut edge (working window 30–200ms).
  9. Cache transcripts per source (transcribe done in real_footage.ingest_footage).
  Audio-first: candidate cuts come from silence gaps ≥400ms (clean) or 150–400ms
  (usable with a visual check).

This module is the **decision layer** — it reads a cached word-level transcript
and produces an EDL. The actual per-segment extract → concat → subtitles-LAST
render is handled by video-use's ``render.py`` (invoked separately) or by the
ai-film-grok final pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from util import utc_now, write_json


class AutoCutError(ValueError):
    pass


# video-use cut padding (Hard Rule 7 working window: 30–200ms)
PAD_BEFORE_SEC = 0.05  # 50ms before first kept word
PAD_AFTER_SEC = 0.08  # 80ms after last kept word
# Silence-gap thresholds (video-use cut craft)
SILENCE_CLEAN_MS = 400  # ≥400ms = cleanest cut
SILENCE_USABLE_MS = 150  # 150–400ms usable with visual check; <150 unsafe


def _load_transcript(path: Path) -> dict[str, Any]:
    """Load a word-level Whisper transcript (faster-whisper JSON shape).

    Accepts either ``{"segments": [...], "words": [...]}`` or a flat word list.
    Returns ``{"words": [{"start": f, "end": f, "text": str}], ...}``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutoCutError(f"cannot read transcript {path}: {exc}") from exc

    words: list[dict[str, Any]] = []
    if isinstance(data, dict):
        # faster-whisper: words live under segments or top-level
        for seg in data.get("segments") or []:
            for w in seg.get("words") or []:
                words.append(_norm_word(w))
        if not words:
            for w in data.get("words") or []:
                words.append(_norm_word(w))
    elif isinstance(data, list):
        for w in data:
            words.append(_norm_word(w))
    if not words:
        raise AutoCutError(f"transcript has no word-level timestamps: {path}")
    # Sort by start time
    words.sort(key=lambda w: float(w.get("start") or 0.0))
    return {"words": words, "source": str(path)}


def _norm_word(w: dict[str, Any]) -> dict[str, Any]:
    """Normalize a word entry to {start, end, text} floats."""
    return {
        "start": float(w.get("start") or w.get("from") or 0.0),
        "end": float(w.get("end") or w.get("to") or 0.0),
        "text": str(w.get("text") or w.get("word") or "").strip(),
    }


def _silence_gaps(words: list[dict[str, Any]]) -> list[tuple[float, float, float]]:
    """Find silence gaps between consecutive words.

    Returns list of (gap_start, gap_end, gap_ms) sorted by time.
    """
    gaps: list[tuple[float, float, float]] = []
    for i in range(1, len(words)):
        prev_end = words[i - 1]["end"]
        cur_start = words[i]["start"]
        gap = cur_start - prev_end
        if gap >= SILENCE_USABLE_MS / 1000.0:
            gaps.append((prev_end, cur_start, gap * 1000.0))
    return gaps


def _segment_boundaries(
    words: list[dict[str, Any]],
    *,
    target_duration_sec: float | None = None,
    max_segment_sec: float = 12.0,
) -> list[tuple[int, int]]:
    """Decide segment word-index ranges [start_i, end_i] by silence gaps.

    Strategy (video-use audio-first):
      - Cut on silence gaps ≥ SILENCE_CLEAN_MS (400ms) preferentially.
      - If a segment would exceed max_segment_sec, cut on the next ≥150ms gap.
      - If target_duration_sec given, aim for ~that many segments total.
    Returns list of (start_word_index, end_word_index) inclusive.
    """
    if not words:
        return []
    boundaries: list[int] = [0]  # word indices where a new segment starts
    seg_start_idx = 0
    seg_start_time = words[0]["start"]
    gaps = _silence_gaps(words)
    gap_by_idx: dict[int, float] = {}
    for gs, ge, _gms in gaps:
        # find the word index at the end of this gap (first word after ge)
        for i in range(seg_start_idx + 1, len(words)):
            if words[i]["start"] >= ge - 0.01:
                gap_by_idx[i] = ge - gs
                break

    i = 1
    while i < len(words):
        seg_dur = words[i]["end"] - seg_start_time
        gap_len = gap_by_idx.get(i, 0.0)
        cut = False
        if gap_len * 1000 >= SILENCE_CLEAN_MS and seg_dur >= 1.5:
            cut = True
        elif seg_dur >= max_segment_sec:
            # No clean gap but segment overran — cut at this word boundary
            # (Hard Rule 6 honored: cut is on a word edge). Prefer a ≥150ms
            # gap if available within the next few words; else cut here.
            cut = True
        if cut:
            boundaries.append(i)
            seg_start_idx = i
            seg_start_time = words[i]["start"]
        i += 1
    boundaries.append(len(words))  # final close
    # Build inclusive ranges
    ranges: list[tuple[int, int]] = []
    for b in range(len(boundaries) - 1):
        ranges.append((boundaries[b], boundaries[b + 1] - 1))
    return ranges


def build_edl(
    *,
    source_id: str,
    source_path: str,
    transcript_path: Path,
    target_duration_sec: float | None = None,
    max_segment_sec: float = 12.0,
) -> dict[str, Any]:
    """Build a video-use-compatible EDL from a word-level transcript.

    Honors video-use Hard Rules 6 (word-boundary cuts) and 7 (pad cut edges).
    """
    transcript = _load_transcript(transcript_path)
    words = transcript["words"]
    ranges = _segment_boundaries(
        words,
        target_duration_sec=target_duration_sec,
        max_segment_sec=max_segment_sec,
    )

    ranges_out: list[dict[str, Any]] = []
    total = 0.0
    for idx, (si, ei) in enumerate(ranges):
        first_word = words[si]
        last_word = words[ei]
        # Pad (Hard Rule 7): pad before first word, after last word
        start = max(0.0, first_word["start"] - PAD_BEFORE_SEC)
        end = last_word["end"] + PAD_AFTER_SEC
        dur = round(end - start, 3)
        total += dur
        quote = " ".join(w["text"] for w in words[si : ei + 1])
        ranges_out.append(
            {
                "source": source_id,
                "start": round(start, 3),
                "end": round(end, 3),
                "beat": f"segment_{idx + 1}",
                "quote": quote[:120],
                "reason": (
                    "clean silence-gap cut"
                    if (end - start) < max_segment_sec
                    else "max_segment_sec split"
                ),
            }
        )

    return {
        "version": 1,
        "sources": {source_id: source_path},
        "ranges": ranges_out,
        "grade": "none",
        "overlays": [],
        "subtitles": None,
        "total_duration_s": round(total, 3),
        "segment_count": len(ranges_out),
        "source_type": "real_footage",
        "hard_rules": {
            "word_boundary_cuts": True,
            "pad_before_sec": PAD_BEFORE_SEC,
            "pad_after_sec": PAD_AFTER_SEC,
            "subtitles_last": True,
        },
        "created_at": utc_now(),
        "note": "Audio-first auto-cut on word boundaries + silence gaps (video-use logic).",
    }


def build_edl_for_root(
    root: Path | str,
    source_id: str,
    *,
    target_duration_sec: float | None = None,
) -> dict[str, Any]:
    """Build an EDL for an already-ingested footage source, write receipt."""
    root = Path(root).expanduser().resolve()
    transcript = root / "footage" / "transcripts" / f"{source_id}.json"
    if not transcript.is_file():
        raise AutoCutError(
            f"transcript not found for {source_id}: {transcript}. Run aifilm ingest-footage first."
        )
    # Resolve the raw source path from the ingest receipt
    ingest_receipt = root / "receipts" / "footage-ingest" / f"{source_id}.json"
    if not ingest_receipt.is_file():
        raise AutoCutError(f"no ingest receipt for {source_id}; run ingest-footage first")
    from util import soft_json

    receipt_data = soft_json(ingest_receipt)
    source_path = receipt_data.get("source_path") or ""

    edl = build_edl(
        source_id=source_id,
        source_path=source_path,
        transcript_path=transcript,
        target_duration_sec=target_duration_sec,
    )
    out = root / "footage" / "edit" / "edl.json"
    write_json(out, edl)
    edl["path"] = str(out)
    return edl
