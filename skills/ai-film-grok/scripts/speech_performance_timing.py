"""Shim — implementation in audio.speech_performance_timing (hard-compat).

Keeps `import speech_performance_timing` working after package move.
"""
from __future__ import annotations

from audio import speech_performance_timing as _impl
import sys as _sys

_sys.modules[__name__] = _impl
