"""Shim — implementation in plan.story_plan (W7 package layout).

Keeps `import story_plan` / `from story_plan import …` working for hard-compat.
"""
from plan import story_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl
