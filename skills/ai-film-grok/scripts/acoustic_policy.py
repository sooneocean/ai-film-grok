"""Shim — implementation in audio.acoustic_policy (W6 package layout).

Keeps `import acoustic_policy` / `from acoustic_policy import …` working for hard-compat.
"""
import sys as _sys

from audio import acoustic_policy as _impl

_sys.modules[__name__] = _impl
