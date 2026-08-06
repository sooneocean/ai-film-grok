"""Shim — implementation in narrative.edit_policy_shared."""

from narrative import edit_policy_shared as _impl
import sys as _sys

_sys.modules[__name__] = _impl
