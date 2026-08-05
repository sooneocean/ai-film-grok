"""Shim — implementation in narrative.dialogue_i2i_route (W7 package layout).

Keeps `import dialogue_i2i_route` / `from dialogue_i2i_route import …` working for hard-compat.
"""
from narrative import dialogue_i2i_route as _impl
import sys as _sys

_sys.modules[__name__] = _impl
