#!/usr/bin/env python3
"""Final mix PARTIAL receipt helpers (P1-B · 2026-08-05)."""
from __future__ import annotations

from pathlib import Path

from util import utc_now, write_json


def write_final_mix_partial_receipt(
    root: Path | str,
    *,
    prior_sc: str,
    error: str,
    mixed: Path | str,
    reason: str = "sidechain_mix_failed_amix_fallback",
    error_type: str | None = None,
    affected_tracks: list[str] | None = None,
) -> Path:
    base = Path(root).expanduser().resolve()
    path = base / "receipts" / "final-mix-partial.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tracks = list(affected_tracks or ["mx", "dx"])
    reason_code = str(reason)
    write_json(
        path,
        {
            "kind": "final-mix-partial",
            "schema_version": 2,
            "at": utc_now(),
            "ok": True,
            "partial": True,
            "reason": reason_code,
            "reason_code": reason_code,
            "from": str(prior_sc),
            "to": "amix_simple",
            "error": str(error)[:300],
            "error_type": str(error_type or "")[:80] or None,
            "affected_tracks": tracks,
            "honest_limits": [
                "sidechain duck unavailable — MX not auto-ducked under DX",
                "not full five-track cinema mix",
                "delivery must remain PARTIAL / not claim full 5-track",
            ],
            "mixed": str(mixed),
        },
    )
    return path
