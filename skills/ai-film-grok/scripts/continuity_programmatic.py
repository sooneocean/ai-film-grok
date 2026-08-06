"""Shim — implementation in gates.continuity_programmatic."""
from gates import continuity_programmatic as _impl
import sys as _sys

_sys.modules[__name__] = _impl
