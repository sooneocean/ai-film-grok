"""Shim — implementation in narrative.dialogue_style (W7 package layout).

Keeps `import dialogue_style` / `from dialogue_style import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_style as _impl

_sys.modules[__name__] = _impl
