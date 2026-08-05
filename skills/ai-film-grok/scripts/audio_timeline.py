"""Shim — implementation in audio.audio_timeline (W6 package layout).

Keeps `import audio_timeline` / `from audio_timeline import …` working for hard-compat.
"""
from audio import audio_timeline as _impl
import sys as _sys

_sys.modules[__name__] = _impl
