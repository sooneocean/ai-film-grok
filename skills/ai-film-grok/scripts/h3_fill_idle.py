"""Shim — implementation in media.h3_fill_idle (W6 package layout).

Keeps `import h3_fill_idle` / `from h3_fill_idle import …` working for hard-compat.
"""
from media import h3_fill_idle as _impl
import sys as _sys

_sys.modules[__name__] = _impl
