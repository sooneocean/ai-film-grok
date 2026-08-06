"""Shim — implementation in narrative.dialogue_style (W7 package layout).

Keeps `import dialogue_style` / `from dialogue_style import …` working for hard-compat.
"""
from narrative import dialogue_style as _impl
import sys as _sys

_sys.modules[__name__] = _impl
