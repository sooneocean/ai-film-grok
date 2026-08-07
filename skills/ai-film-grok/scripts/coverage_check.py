"""Shim — implementation in plan.coverage_check (Film Production OS W3)."""
import sys as _sys

from plan import coverage_check as _impl

_sys.modules[__name__] = _impl
