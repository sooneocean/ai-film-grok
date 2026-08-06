"""Shim — implementation in plan.shot_review (W7 package layout).

Keeps `import shot_review` / `from shot_review import …` working for hard-compat.
"""
import sys as _sys

from plan import shot_review as _impl

_sys.modules[__name__] = _impl
