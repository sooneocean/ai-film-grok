"""Shim — implementation in audio.ambience_candidates (W6 package layout).

Keeps `import ambience_candidates` / `from ambience_candidates import …` working for hard-compat.
"""
import sys as _sys

from audio import ambience_candidates as _impl

_sys.modules[__name__] = _impl
