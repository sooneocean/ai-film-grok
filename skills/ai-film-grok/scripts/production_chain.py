"""Shim — implementation in plan.production_chain (W7 package layout).

Keeps `import production_chain` / `from production_chain import …` working for hard-compat.
"""
from plan import production_chain as _impl
import sys as _sys

_sys.modules[__name__] = _impl
