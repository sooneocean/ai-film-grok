"""Shim — implementation in audio.lipsync_backend (W6 package layout).

Keeps `import lipsync_backend` / `from lipsync_backend import …` working for hard-compat.
"""
from audio import lipsync_backend as _impl
import sys as _sys

_sys.modules[__name__] = _impl
