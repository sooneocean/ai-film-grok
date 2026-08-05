"""Shim — implementation in audio.event_voice_stem (W6 package layout).

Keeps `import event_voice_stem` / `from event_voice_stem import …` working for hard-compat.
"""
from audio import event_voice_stem as _impl
import sys as _sys

_sys.modules[__name__] = _impl
