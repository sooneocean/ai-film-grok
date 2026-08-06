"""Shim — implementation in plan.story_normalize (W7 package layout).

Keeps `import story_normalize` / `from story_normalize import …` working for hard-compat.
"""
import sys as _sys

from plan import story_normalize as _impl

_sys.modules[__name__] = _impl
