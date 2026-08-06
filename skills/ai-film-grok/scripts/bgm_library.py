"""Shim — implementation in audio.bgm_library (W6 package layout).

Keeps `import bgm_library` / `from bgm_library import …` working for hard-compat.
"""
from audio import bgm_library as _impl
import sys as _sys

_sys.modules[__name__] = _impl
