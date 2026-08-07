"""Shim — implementation in plan.story_structure (Film Production OS W1)."""
import sys as _sys

from plan import story_structure as _impl

_sys.modules[__name__] = _impl
