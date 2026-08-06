"""Shim — implementation in plan.production_report (W7 package layout).

Keeps `import production_report` / `from production_report import …` working for hard-compat.
"""
from plan import production_report as _impl
import sys as _sys

_sys.modules[__name__] = _impl
