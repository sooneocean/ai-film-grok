"""Shim — implementation in narrative.dialogue_broll (W7 package layout).

Keeps `import dialogue_broll` / `from dialogue_broll import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_broll as _impl

_sys.modules[__name__] = _impl
