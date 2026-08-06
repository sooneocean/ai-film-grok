"""Shim — implementation in plan.production_truth (W7 package layout).

Keeps `import production_truth` / `from production_truth import …` working for hard-compat.
"""
import sys as _sys

from plan import production_truth as _impl

_sys.modules[__name__] = _impl
