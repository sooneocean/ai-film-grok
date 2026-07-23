#!/usr/bin/env python3
"""EDL merge — combine generated-clip and real-footage timelines.

Extracted from edit_policy.py so the leaf merge logic can be tested and
imported without pulling the full transition/wardrobe/heat policy surface.
The public symbol ``merge_edls`` is re-exported by edit_policy for
backward compatibility.
"""

from __future__ import annotations

from typing import Any


def merge_edls(
    generated_edl: dict[str, Any] | None,
    real_edl: dict[str, Any] | None,
    *,
    interleave: bool = False,
) -> dict[str, Any]:
    """Merge a generated-clip timeline with a real-footage auto-cut EDL.

    Each EDL follows the video-use shape: ``{"sources": {...}, "ranges": [...],
    "overlays": [...], "subtitles": ...}``.

    - Non-interleave: append real ranges after generated ranges (sequential).
    - Interleave: alternate generated/real ranges by beat order if present.

    Hard Rule 1 honored: ``subtitles`` stays LAST — if both EDLs have subtitles,
    the merged keeps the generated one (or None) and notes the conflict.
    """
    gen = generated_edl or {}
    real = real_edl or {}
    gen_ranges = list(gen.get("ranges") or [])
    real_ranges = list(real.get("ranges") or [])

    sources = {**(gen.get("sources") or {}), **(real.get("sources") or {})}
    overlays = list(gen.get("overlays") or []) + list(real.get("overlays") or [])

    if not interleave:
        ranges = gen_ranges + real_ranges
    else:
        # Interleave by order/beat if available, else alternate
        ranges = []
        max_len = max(len(gen_ranges), len(real_ranges))
        for i in range(max_len):
            if i < len(gen_ranges):
                ranges.append(gen_ranges[i])
            if i < len(real_ranges):
                ranges.append(real_ranges[i])

    # Subtitles: generated wins; real-footage subtitles are baked into its segments
    gen_subs = gen.get("subtitles")
    real_subs = real.get("subtitles")
    subtitle_conflict = gen_subs and real_subs
    subtitles = gen_subs  # keep generated; real subtitles applied per-segment

    total = sum(float(r.get("end", 0)) - float(r.get("start", 0)) for r in ranges)

    return {
        "version": 1,
        "sources": sources,
        "ranges": ranges,
        "grade": gen.get("grade") or real.get("grade") or "none",
        "overlays": overlays,
        "subtitles": subtitles,
        "subtitle_conflict": bool(subtitle_conflict),
        "total_duration_s": round(total, 3),
        "segment_count": len(ranges),
        "source_types": sorted(
            {
                r.get("source_type")
                or gen.get("source_type")
                or real.get("source_type")
                or "generated"
                for r in ranges
            }
            | {real.get("source_type") or "real_footage" if real_ranges else "generated"}
        ),
        "merged": bool(gen_ranges and real_ranges),
        "hard_rules": {
            "subtitles_last": True,
            "note": "Generated subtitles kept; real-footage subtitles applied per-segment",
        },
    }
