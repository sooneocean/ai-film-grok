"""Tombstone — LatentSync adapter removed (v2.40)."""
from audio.lipsync_backend import LIPSYNC_FROZEN_MSG, LipSyncError

def run(*_a, **_k):
    raise LipSyncError(LIPSYNC_FROZEN_MSG)
