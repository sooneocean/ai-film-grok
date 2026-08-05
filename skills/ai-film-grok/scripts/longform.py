"""Shim — implementation in plan.longform (W7 package layout).

Keeps `import longform` / `from longform import …` working for hard-compat.
"""
from plan import longform as _impl
import sys as _sys

_sys.modules[__name__] = _impl
