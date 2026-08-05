"""Shim — implementation in narrative.dramatic_meaning (W7 package layout).

Keeps `import dramatic_meaning` / `from dramatic_meaning import …` working for hard-compat.
"""
from narrative import dramatic_meaning as _impl
import sys as _sys

_sys.modules[__name__] = _impl
