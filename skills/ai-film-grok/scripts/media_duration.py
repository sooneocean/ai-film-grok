"""Shim — implementation in media.media_duration (W6 package layout).

Keeps `import media_duration` / `from media_duration import …` working for hard-compat.
"""
import sys as _sys

from media import media_duration as _impl

_sys.modules[__name__] = _impl
