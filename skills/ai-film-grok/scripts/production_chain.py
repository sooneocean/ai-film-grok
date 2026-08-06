"""Shim — implementation in plan.production_chain (W7 package layout).

Keeps `import production_chain` / `from production_chain import …` working for hard-compat.
"""
import sys as _sys

from plan import production_chain as _impl

_sys.modules[__name__] = _impl
