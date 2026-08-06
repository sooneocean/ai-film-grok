"""Shim — implementation in narrative.dialogue_screenplay (W7 package layout).

Keeps `import dialogue_screenplay` / `from dialogue_screenplay import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_screenplay as _impl

_sys.modules[__name__] = _impl
