"""Shim — implementation in narrative.edit_policy_heat (W4)."""
from narrative import edit_policy_heat as _impl
import sys as _sys
_sys.modules[__name__] = _impl
