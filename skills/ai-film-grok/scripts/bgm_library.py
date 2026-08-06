"""Shim — implementation in audio.bgm_library (W6 package layout).

Keeps `import bgm_library` / `from bgm_library import …` working for hard-compat.
"""
import sys as _sys

from audio import bgm_library as _impl

_sys.modules[__name__] = _impl
