"""Shim — implementation in audio.audio_node_service (W6 package layout).

Keeps `import audio_node_service` / `from audio_node_service import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_node_service as _impl

_sys.modules[__name__] = _impl
