"""Shim — implementation in narrative.dialogue_broll (W7 package layout).

Keeps `import dialogue_broll` / `from dialogue_broll import …` working for hard-compat.
"""
from narrative import dialogue_broll as _impl
import sys as _sys

_sys.modules[__name__] = _impl
