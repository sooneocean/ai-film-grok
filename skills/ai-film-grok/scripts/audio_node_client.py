"""Shim — implementation in audio.audio_node_client (W6 package layout).

Keeps `import audio_node_client` / `from audio_node_client import …` working for hard-compat.
"""
from audio import audio_node_client as _impl
import sys as _sys

_sys.modules[__name__] = _impl
