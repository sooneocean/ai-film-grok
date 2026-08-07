"""Shim — implementation in plan.revise_plan (Film Production OS W6)."""
import sys as _sys

from plan import revise_plan as _impl

_sys.modules[__name__] = _impl
