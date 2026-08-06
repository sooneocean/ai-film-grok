"""Shim — implementation in plan.longform (W7 package layout).

Keeps `import longform` / `from longform import …` working for hard-compat.
"""
import sys as _sys

from plan import longform as _impl

_sys.modules[__name__] = _impl
