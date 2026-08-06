"""Shim — implementation in plan.shot_package (W7 package layout).

Keeps `import shot_package` / `from shot_package import …` working for hard-compat.
"""
import sys as _sys

from plan import shot_package as _impl

_sys.modules[__name__] = _impl
