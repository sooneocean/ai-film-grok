"""Shim — implementation in audio.speech_preview (hard-compat).

Keeps `import speech_preview` working after package move.
"""
from __future__ import annotations

import sys as _sys

from audio import speech_preview as _impl

_sys.modules[__name__] = _impl
