#!/usr/bin/env python3
"""FRW lipsync client removed (v2.40) — tombstone only."""

from __future__ import annotations

from typing import Any

from audio.lipsync_backend import LIPSYNC_FROZEN_MSG, LipSyncError


def probe() -> dict[str, Any]:
    return {"ok": False, "frozen": True, "message": LIPSYNC_FROZEN_MSG}


def run_frw_lipsync(*_a: Any, **_k: Any) -> dict[str, Any]:
    raise LipSyncError(LIPSYNC_FROZEN_MSG)


def main(argv: list[str] | None = None) -> int:
    del argv
    print(LIPSYNC_FROZEN_MSG)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
