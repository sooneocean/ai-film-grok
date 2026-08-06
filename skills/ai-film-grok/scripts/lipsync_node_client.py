"""Shim — implementation in audio.lipsync_node_client (W6 package layout).

Keeps `import lipsync_node_client` / `from lipsync_node_client import …` working for hard-compat.
"""
import sys as _sys

from audio import lipsync_node_client as _impl

_sys.modules[__name__] = _impl
