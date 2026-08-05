"""Shim — implementation in narrative.edit_strategy (W7 package layout).

Keeps `import edit_strategy` / `from edit_strategy import …` working for hard-compat.
"""
from narrative import edit_strategy as _impl
import sys as _sys

_sys.modules[__name__] = _impl
