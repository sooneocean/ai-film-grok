"""Shim — implementation in audio.audio_provenance (W6 package layout).

Keeps `import audio_provenance` / `from audio_provenance import …` working for hard-compat.
"""
from audio import audio_provenance as _impl
import sys as _sys

_sys.modules[__name__] = _impl
