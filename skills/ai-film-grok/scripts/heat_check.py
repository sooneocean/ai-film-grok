"""Shim — implementation in narrative.heat_check (W7 package layout).

Keeps `import heat_check` / `from heat_check import …` working for hard-compat.
"""
from narrative import heat_check as _impl
import sys as _sys

_sys.modules[__name__] = _impl
