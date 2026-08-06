"""Shim — implementation in audio.mmaudio_runner (W6 package layout).

Keeps `import mmaudio_runner` / `from mmaudio_runner import …` working for hard-compat.
"""
import sys as _sys

from audio import mmaudio_runner as _impl

_sys.modules[__name__] = _impl
