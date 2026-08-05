"""Shim — implementation in audio.vibevoice_asr_review (W6 package layout).

Keeps `import vibevoice_asr_review` / `from vibevoice_asr_review import …` working for hard-compat.
"""
from audio import vibevoice_asr_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl
