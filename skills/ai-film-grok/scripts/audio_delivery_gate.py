"""Shim — implementation in audio.audio_delivery_gate (W6 package layout).

Keeps `import audio_delivery_gate` / `from audio_delivery_gate import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_delivery_gate as _impl

_sys.modules[__name__] = _impl
