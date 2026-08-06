"""Shim — implementation in audio.bgm_candidates (W6 package layout).

Keeps `import bgm_candidates` / `from bgm_candidates import …` working for hard-compat.
"""
from audio import bgm_candidates as _impl
import sys as _sys

_sys.modules[__name__] = _impl
