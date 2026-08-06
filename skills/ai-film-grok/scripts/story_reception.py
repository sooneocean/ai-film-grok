"""Shim — implementation in plan.story_reception (W7 package layout).

Keeps `import story_reception` / `from story_reception import …` working for hard-compat.
"""
import sys as _sys

from plan import story_reception as _impl

_sys.modules[__name__] = _impl
