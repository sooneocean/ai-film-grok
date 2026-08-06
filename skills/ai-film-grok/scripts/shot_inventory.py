"""Shim — implementation in plan.shot_inventory (W7 package layout).

Keeps `import shot_inventory` / `from shot_inventory import …` working for hard-compat.
"""
from plan import shot_inventory as _impl
import sys as _sys

_sys.modules[__name__] = _impl
