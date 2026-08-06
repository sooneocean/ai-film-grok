"""Shim — implementation in media.still_source (W6 package layout).

Keeps `import still_source` / `from still_source import …` working for hard-compat.
"""
import sys as _sys

from media import still_source as _impl

_sys.modules[__name__] = _impl
