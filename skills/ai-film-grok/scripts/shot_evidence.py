"""Shim — implementation in plan.shot_evidence (W7 package layout).

Keeps `import shot_evidence` / `from shot_evidence import …` working for hard-compat.
"""
from plan import shot_evidence as _impl
import sys as _sys

_sys.modules[__name__] = _impl
