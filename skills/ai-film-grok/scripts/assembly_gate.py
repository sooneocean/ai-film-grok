"""Shim — implementation in plan.assembly_gate (Film Production OS W6)."""
import sys as _sys

from plan import assembly_gate as _impl

_sys.modules[__name__] = _impl
