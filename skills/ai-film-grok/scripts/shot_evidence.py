"""Shim — implementation in plan.shot_evidence (W7 package layout).

Keeps `import shot_evidence` / `from shot_evidence import …` working for hard-compat.
"""
import sys as _sys

from plan import shot_evidence as _impl

_sys.modules[__name__] = _impl
