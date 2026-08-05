"""Shim — implementation in plan.production_truth (W7 package layout).

Keeps `import production_truth` / `from production_truth import …` working for hard-compat.
"""
from plan import production_truth as _impl
import sys as _sys

_sys.modules[__name__] = _impl
