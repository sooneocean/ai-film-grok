"""Shim — implementation in audio.speech_performance_timing (hard-compat).

Keeps `import speech_performance_timing` working after package move.
"""
from __future__ import annotations

import sys as _sys

from audio import speech_performance_timing as _impl

_sys.modules[__name__] = _impl
