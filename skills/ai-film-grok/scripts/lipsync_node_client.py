"""Shim — implementation in audio.lipsync_node_client (W6 package layout).

Keeps `import lipsync_node_client` / `from lipsync_node_client import …` working for hard-compat.
"""
from audio import lipsync_node_client as _impl
import sys as _sys

_sys.modules[__name__] = _impl
