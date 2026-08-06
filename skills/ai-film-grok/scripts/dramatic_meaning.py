"""Shim — implementation in narrative.dramatic_meaning (W7 package layout).

Keeps `import dramatic_meaning` / `from dramatic_meaning import …` working for hard-compat.
"""
import sys as _sys

from narrative import dramatic_meaning as _impl

_sys.modules[__name__] = _impl
