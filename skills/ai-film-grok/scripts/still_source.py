"""Shim — implementation in media.still_source (W6 package layout).

Keeps `import still_source` / `from still_source import …` working for hard-compat.
"""
from media import still_source as _impl
import sys as _sys

_sys.modules[__name__] = _impl
