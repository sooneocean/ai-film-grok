"""Shim — implementation in audio.audio_delivery_gate (W6 package layout).

Keeps `import audio_delivery_gate` / `from audio_delivery_gate import …` working for hard-compat.
"""
from audio import audio_delivery_gate as _impl
import sys as _sys

_sys.modules[__name__] = _impl
