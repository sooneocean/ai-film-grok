"""Tombstone — lipsync node client removed (v2.40)."""

from __future__ import annotations

from typing import Any

from audio.lipsync_backend import LIPSYNC_FROZEN_MSG, LipSyncError

LipsyncNodeError = LipSyncError


def health(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {"ok": False, "frozen": True, "message": LIPSYNC_FROZEN_MSG}


def render(*_a: Any, **_k: Any) -> dict[str, Any]:
    raise LipSyncError(LIPSYNC_FROZEN_MSG)


def _multipart(*_a: Any, **_k: Any) -> Any:
    raise LipSyncError(LIPSYNC_FROZEN_MSG)


def _request(*_a: Any, **_k: Any) -> Any:
    raise LipSyncError(LIPSYNC_FROZEN_MSG)


def _url(*_a: Any, **_k: Any) -> str:
    raise LipSyncError(LIPSYNC_FROZEN_MSG)
