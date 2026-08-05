"""Shim — implementation in plan.story_contract (W7 package layout).

Keeps `import story_contract` / `from story_contract import …` working for hard-compat.
"""
from plan import story_contract as _impl
import sys as _sys

_sys.modules[__name__] = _impl
