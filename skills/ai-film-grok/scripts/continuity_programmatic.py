"""Shim — implementation in gates.continuity_programmatic."""
import sys as _sys

from gates import continuity_programmatic as _impl

_sys.modules[__name__] = _impl
