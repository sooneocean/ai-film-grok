"""Shim — implementation in media.pilot_review (W6 package layout).

Keeps `import pilot_review` / `from pilot_review import …` working for hard-compat.
"""
from media import pilot_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl
