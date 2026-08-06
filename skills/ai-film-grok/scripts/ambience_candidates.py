"""Shim — implementation in audio.ambience_candidates (W6 package layout).

Keeps `import ambience_candidates` / `from ambience_candidates import …` working for hard-compat.
"""
from audio import ambience_candidates as _impl
import sys as _sys

_sys.modules[__name__] = _impl
