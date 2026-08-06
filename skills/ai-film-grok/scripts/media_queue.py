"""Shim — implementation in media.media_queue (W6 package layout).

Keeps `import media_queue` / `from media_queue import …` working for hard-compat.
"""
from media import media_queue as _impl
import sys as _sys

_sys.modules[__name__] = _impl
