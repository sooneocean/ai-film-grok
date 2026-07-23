#!/usr/bin/env python3
"""Fail-loud media duration probe (three-axis / duration truth sediment).

No silent fake defaults (3.0 / 6.0 / 30.0) on unreadable or missing media.
Used by final/compose paths so subtitle/VO/video clocks cannot drift unnoticed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from media_probe import MediaProbeError, probe_media


class MediaDurationError(RuntimeError):
    pass


def probe_duration_sec(
    path: Path | str,
    *,
    label: str = "media",
    min_sec: float = 0.01,
) -> float:
    """Return media duration in seconds. Raises MediaDurationError on any failure."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise MediaDurationError(f"{label}: missing or not a file: {p}")
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise MediaDurationError(f"{label}: cannot stat {p}: {exc}") from exc
    if size <= 0:
        raise MediaDurationError(f"{label}: empty file (0 bytes): {p}")

    try:
        report = probe_media(p)
    except MediaProbeError as exc:
        raise MediaDurationError(f"{label}: {exc}") from exc
    raw = str((report.get("format") or {}).get("duration") or "").strip()
    if not raw or raw.lower() in {"n/a", "nan", "inf", "-inf"}:
        raise MediaDurationError(f"{label}: unreadable duration from ffprobe on {p}: {raw!r}")
    try:
        dur = float(raw)
    except ValueError as exc:
        raise MediaDurationError(f"{label}: non-numeric duration {raw!r} for {p}") from exc
    if dur != dur or dur <= 0:  # NaN or non-positive
        raise MediaDurationError(f"{label}: invalid duration {dur} for {p}")
    if dur < min_sec:
        raise MediaDurationError(f"{label}: duration {dur}s below min {min_sec}s for {p}")
    return float(dur)


def probe_duration_sec_or_raise(
    path: Path | str,
    *,
    label: str = "media",
) -> float:
    """Alias kept for call sites that want explicit raise semantics."""
    return probe_duration_sec(path, label=label)


def duration_receipt_fields(path: Path | str, *, label: str = "media") -> dict[str, Any]:
    """Probe and return structured fields for receipts (never invents duration)."""
    p = Path(path).expanduser().resolve()
    dur = probe_duration_sec(p, label=label)
    return {
        "path": str(p),
        "duration_sec": dur,
        "bytes": p.stat().st_size,
        "label": label,
        "source": "ffprobe",
    }
