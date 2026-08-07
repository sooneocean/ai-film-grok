"""Shim — implementation in plan.prompt_compiler (Film Production OS W5)."""
import sys as _sys

from plan import prompt_compiler as _impl

_sys.modules[__name__] = _impl
