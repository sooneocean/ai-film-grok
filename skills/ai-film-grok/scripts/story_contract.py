"""Shim — implementation in plan.story_contract (W7 package layout).

Keeps `import story_contract` / `from story_contract import …` working for hard-compat.
"""
import sys as _sys

from plan import story_contract as _impl

_sys.modules[__name__] = _impl
