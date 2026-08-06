"""Shim — implementation in gates.narrative_rebind."""
import sys as _sys

from gates import narrative_rebind as _impl

_sys.modules[__name__] = _impl
