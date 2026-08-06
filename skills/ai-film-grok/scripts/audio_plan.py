"""Shim — implementation in audio.audio_plan (W6 package layout).

Keeps `import audio_plan` / `from audio_plan import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_plan as _impl

_sys.modules[__name__] = _impl
