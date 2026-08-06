"""Shim — implementation in media.still_challenge (W6 package layout).

Keeps `import still_challenge` / `from still_challenge import …` working for hard-compat.
"""
from media import still_challenge as _impl
import sys as _sys

_sys.modules[__name__] = _impl
