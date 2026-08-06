"""Shim — implementation in narrative.adult_max_director (W7 package layout).

Keeps `import adult_max_director` / `from adult_max_director import …` working for hard-compat.
"""
import sys as _sys

from narrative import adult_max_director as _impl

_sys.modules[__name__] = _impl
