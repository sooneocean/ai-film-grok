"""Shim — implementation in media.media_probe (W6 package layout).

Keeps `import media_probe` / `from media_probe import …` working for hard-compat.
"""
from media import media_probe as _impl
import sys as _sys

_sys.modules[__name__] = _impl
