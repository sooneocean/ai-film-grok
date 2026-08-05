"""Shim — implementation in media.media_duration (W6 package layout).

Keeps `import media_duration` / `from media_duration import …` working for hard-compat.
"""
from media import media_duration as _impl
import sys as _sys

_sys.modules[__name__] = _impl
