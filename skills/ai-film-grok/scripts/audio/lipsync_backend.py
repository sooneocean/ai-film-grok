#!/usr/bin/env python3
"""Post lipsync stack removed (v2.40) — production uses native audio only.

Historical LatentSync / MuseTalk / Wav2Lip / FRW lipsync are frozen tombstones.
Dialogue talking heads: Grok Video / H3 with prefer_native. See references/lipsync.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LIPSYNC_FROZEN_MSG = (
    "post lipsync is removed from production (ai-film-grok ≥2.40). "
    "Use prefer_native / use_clip_audio on Grok or H3 dialogue clips; "
    "final --lipsync off only. See references/lipsync.md."
)


class LipSyncError(RuntimeError):
    """Raised when any post-process lipsync path is requested."""


def probe() -> dict[str, Any]:
    return {
        "ok": True,
        "frozen": True,
        "env_backend": "off",
        "ready": [],
        "backends": {},
        "message": LIPSYNC_FROZEN_MSG,
    }


def should_lipsync_shot(_shot: dict[str, Any] | None = None) -> bool:
    return False


def enforce_dialogue_lipsync(
    *,
    vo_mode: str,
    shots: list[dict[str, Any]],
    requested: str,
) -> str:
    """Only ``off`` is allowed; any other mode is a hard error."""
    del vo_mode, shots
    mode = (requested or "off").strip().lower() or "off"
    if mode != "off":
        raise LipSyncError(f"{LIPSYNC_FROZEN_MSG} (got --lipsync {mode!r})")
    return "off"


def lipsync_one(
    *,
    video: Path | str,
    audio: Path | str,
    out: Path | str,
    backend: str = "off",
    **_kwargs: Any,
) -> dict[str, Any]:
    del video, audio, out, backend
    raise LipSyncError(LIPSYNC_FROZEN_MSG)


def main(argv: list[str] | None = None) -> int:
    del argv
    print(LIPSYNC_FROZEN_MSG)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
