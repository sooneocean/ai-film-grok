"""Shim — implementation in plan.production_team (W7 package layout).

Keeps `import production_team` / `from production_team import …` working for hard-compat.
"""
import sys as _sys

from plan import production_team as _impl

_sys.modules[__name__] = _impl
