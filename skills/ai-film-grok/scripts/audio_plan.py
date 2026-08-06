"""Shim — implementation in audio.audio_plan (W6 package layout).

Keeps `import audio_plan` / `from audio_plan import …` working for hard-compat.
"""
from audio import audio_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl
