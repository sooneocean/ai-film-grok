"""Shim — implementation in plan.story_plan (W7 package layout).

Keeps `import story_plan` / `from story_plan import …` working for hard-compat.
"""
import sys as _sys

from plan import story_plan as _impl

_sys.modules[__name__] = _impl
