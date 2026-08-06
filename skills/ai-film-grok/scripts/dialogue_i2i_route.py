"""Shim — implementation in narrative.dialogue_i2i_route (W7 package layout).

Keeps `import dialogue_i2i_route` / `from dialogue_i2i_route import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_i2i_route as _impl

_sys.modules[__name__] = _impl
