"""Shim — implementation in audio.elevenlabs_canary (hard-compat).

Keeps `import elevenlabs_canary` working after package move.
"""
from __future__ import annotations

from audio import elevenlabs_canary as _impl
import sys as _sys

_sys.modules[__name__] = _impl
