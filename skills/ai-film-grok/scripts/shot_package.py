"""Shim — implementation in plan.shot_package (W7 package layout).

Keeps `import shot_package` / `from shot_package import …` working for hard-compat.
"""
from plan import shot_package as _impl
import sys as _sys

_sys.modules[__name__] = _impl
