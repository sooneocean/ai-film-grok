"""Shim — implementation in plan.story_quality (W7 package layout).

Keeps `import story_quality` / `from story_quality import …` working for hard-compat.
"""
import sys as _sys

from plan import story_quality as _impl

_sys.modules[__name__] = _impl
