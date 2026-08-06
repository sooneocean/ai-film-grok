"""Shim — implementation in plan.shot_review (W7 package layout).

Keeps `import shot_review` / `from shot_review import …` working for hard-compat.
"""
from plan import shot_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl
