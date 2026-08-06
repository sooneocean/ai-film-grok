"""Shim — implementation in audio.mmaudio_adapter (W6 package layout).

Keeps `import mmaudio_adapter` / `from mmaudio_adapter import …` working for hard-compat.
"""
import sys as _sys

from audio import mmaudio_adapter as _impl

_sys.modules[__name__] = _impl
