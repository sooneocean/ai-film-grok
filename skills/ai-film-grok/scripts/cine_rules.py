"""Shim — implementation in plan.cine_rules (Film Production OS W7)."""
import sys as _sys

from plan import cine_rules as _impl

_sys.modules[__name__] = _impl
