"""Shim — implementation in plan.story_reception (W7 package layout).

Keeps `import story_reception` / `from story_reception import …` working for hard-compat.
"""
from plan import story_reception as _impl
import sys as _sys

_sys.modules[__name__] = _impl
