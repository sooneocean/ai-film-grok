"""Shim — implementation in audio.audio_timeline (W6 package layout).

Keeps `import audio_timeline` / `from audio_timeline import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_timeline as _impl

_sys.modules[__name__] = _impl
