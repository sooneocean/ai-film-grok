"""Shim — implementation in plan.story_quality (W7 package layout).

Keeps `import story_quality` / `from story_quality import …` working for hard-compat.
"""
from plan import story_quality as _impl
import sys as _sys

_sys.modules[__name__] = _impl
