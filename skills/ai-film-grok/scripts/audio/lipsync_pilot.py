"""Tombstone — lipsync pilot removed (v2.40)."""

from audio.lipsync_backend import LIPSYNC_FROZEN_MSG, LipSyncError

LipsyncPilotError = LipSyncError


def run_lipsync_pilot(*_a, **_k):
    raise LipSyncError(LIPSYNC_FROZEN_MSG)
