"""Shim — implementation in media.media_probe (W6 package layout).

Keeps `import media_probe` / `from media_probe import …` working for hard-compat.
"""
import sys as _sys

from media import media_probe as _impl

_sys.modules[__name__] = _impl
