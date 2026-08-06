"""Shim — implementation in narrative.edit_policy (W7 package layout).

Keeps `import edit_policy` / `from edit_policy import …` working for hard-compat.
"""
import sys as _sys

from narrative import edit_policy as _impl

_sys.modules[__name__] = _impl
