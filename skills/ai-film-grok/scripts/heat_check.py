"""Shim — implementation in narrative.heat_check (W7 package layout).

Keeps `import heat_check` / `from heat_check import …` working for hard-compat.
"""
import sys as _sys

from narrative import heat_check as _impl

_sys.modules[__name__] = _impl
