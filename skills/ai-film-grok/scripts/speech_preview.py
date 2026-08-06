"""Shim — implementation in audio.speech_preview (hard-compat).

Keeps `import speech_preview` working after package move.
"""
from __future__ import annotations

from audio import speech_preview as _impl
import sys as _sys

_sys.modules[__name__] = _impl
