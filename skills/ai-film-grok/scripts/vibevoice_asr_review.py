"""Shim — implementation in audio.vibevoice_asr_review (W6 package layout).

Keeps `import vibevoice_asr_review` / `from vibevoice_asr_review import …` working for hard-compat.
"""
import sys as _sys

from audio import vibevoice_asr_review as _impl

_sys.modules[__name__] = _impl
