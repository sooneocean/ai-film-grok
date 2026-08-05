"""Shim — implementation in narrative.dialogue_screenplay (W7 package layout).

Keeps `import dialogue_screenplay` / `from dialogue_screenplay import …` working for hard-compat.
"""
from narrative import dialogue_screenplay as _impl
import sys as _sys

_sys.modules[__name__] = _impl
