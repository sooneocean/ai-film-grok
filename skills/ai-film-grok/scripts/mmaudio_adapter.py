"""Shim — implementation in audio.mmaudio_adapter (W6 package layout).

Keeps `import mmaudio_adapter` / `from mmaudio_adapter import …` working for hard-compat.
"""
from audio import mmaudio_adapter as _impl
import sys as _sys

_sys.modules[__name__] = _impl
