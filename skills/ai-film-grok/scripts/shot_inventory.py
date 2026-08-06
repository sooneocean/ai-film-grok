"""Shim — implementation in plan.shot_inventory (W7 package layout).

Keeps `import shot_inventory` / `from shot_inventory import …` working for hard-compat.
"""
import sys as _sys

from plan import shot_inventory as _impl

_sys.modules[__name__] = _impl
