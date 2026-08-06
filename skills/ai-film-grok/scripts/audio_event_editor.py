"""Shim — implementation in audio.audio_event_editor (W6 package layout).

Keeps `import audio_event_editor` / `from audio_event_editor import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_event_editor as _impl

_sys.modules[__name__] = _impl
