"""Shim — implementation in audio.audio_node_client (W6 package layout).

Keeps `import audio_node_client` / `from audio_node_client import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_node_client as _impl

_sys.modules[__name__] = _impl
