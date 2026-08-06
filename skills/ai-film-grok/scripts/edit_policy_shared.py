"""Shim — implementation in narrative.edit_policy_shared."""

import sys as _sys

from narrative import edit_policy_shared as _impl

_sys.modules[__name__] = _impl
