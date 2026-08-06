"""Shim — implementation in media.h3_fill_idle (W6 package layout).

Keeps `import h3_fill_idle` / `from h3_fill_idle import …` working for hard-compat.
"""
import sys as _sys

from media import h3_fill_idle as _impl

_sys.modules[__name__] = _impl
