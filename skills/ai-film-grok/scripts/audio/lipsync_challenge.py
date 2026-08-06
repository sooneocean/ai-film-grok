"""Tombstone — lipsync challenge removed (v2.40)."""

from audio.lipsync_backend import LIPSYNC_FROZEN_MSG, LipSyncError

LipsyncChallengeError = LipSyncError


def run_lipsync_challenge(*_a, **_k):
    raise LipSyncError(LIPSYNC_FROZEN_MSG)
