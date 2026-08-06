"""Shim — implementation in media.pilot_review (W6 package layout).

Keeps `import pilot_review` / `from pilot_review import …` working for hard-compat.
"""
import sys as _sys

from media import pilot_review as _impl

_sys.modules[__name__] = _impl
