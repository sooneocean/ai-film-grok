"""Shim — implementation in audio.bgm_candidates (W6 package layout).

Keeps `import bgm_candidates` / `from bgm_candidates import …` working for hard-compat.
"""
import sys as _sys

from audio import bgm_candidates as _impl

_sys.modules[__name__] = _impl
