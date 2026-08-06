"""Shim — implementation in audio.audio_provenance (W6 package layout).

Keeps `import audio_provenance` / `from audio_provenance import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_provenance as _impl

_sys.modules[__name__] = _impl
