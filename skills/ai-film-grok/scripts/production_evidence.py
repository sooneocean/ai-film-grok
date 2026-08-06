"""Shim — implementation in plan.production_evidence (W7 package layout).

Keeps `import production_evidence` / `from production_evidence import …` working for hard-compat.
"""
from plan import production_evidence as _impl
import sys as _sys

_sys.modules[__name__] = _impl
