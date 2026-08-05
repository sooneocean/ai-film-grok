"""Shim — implementation in plan.production_team (W7 package layout).

Keeps `import production_team` / `from production_team import …` working for hard-compat.
"""
from plan import production_team as _impl
import sys as _sys

_sys.modules[__name__] = _impl
