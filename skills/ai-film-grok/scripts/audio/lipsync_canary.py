"""Tombstone — lipsync canary removed (v2.40)."""

from audio.lipsync_backend import LIPSYNC_FROZEN_MSG, LipSyncError

LipsyncCanaryError = LipSyncError


def run_lipsync_canary(*_a, **_k):
    raise LipSyncError(LIPSYNC_FROZEN_MSG)
