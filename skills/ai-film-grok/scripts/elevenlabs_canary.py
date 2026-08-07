"""Shim — implementation in audio.elevenlabs_canary (hard-compat).

Keeps `import elevenlabs_canary` working after package move.
"""
from __future__ import annotations

import sys as _sys

from audio import elevenlabs_canary as _impl

_sys.modules[__name__] = _impl
