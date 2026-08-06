"""Shim — implementation in narrative.adult_max_director (W7 package layout).

Keeps `import adult_max_director` / `from adult_max_director import …` working for hard-compat.
"""
from narrative import adult_max_director as _impl
import sys as _sys

_sys.modules[__name__] = _impl
