"""Shim — implementation in audio.audio_event_editor (W6 package layout).

Keeps `import audio_event_editor` / `from audio_event_editor import …` working for hard-compat.
"""
from audio import audio_event_editor as _impl
import sys as _sys

_sys.modules[__name__] = _impl
