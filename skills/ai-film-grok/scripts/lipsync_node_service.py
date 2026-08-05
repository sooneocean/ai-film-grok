"""Shim — implementation in audio.lipsync_node_service (W6 package layout).

Keeps `import lipsync_node_service` / `from lipsync_node_service import …` working for hard-compat.
"""
from audio import lipsync_node_service as _impl
import sys as _sys

_sys.modules[__name__] = _impl
