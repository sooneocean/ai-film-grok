"""Shim — implementation in plan.production_evidence (W7 package layout).

Keeps `import production_evidence` / `from production_evidence import …` working for hard-compat.
"""
import sys as _sys

from plan import production_evidence as _impl

_sys.modules[__name__] = _impl
