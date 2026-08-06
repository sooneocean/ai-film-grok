"""Shim — implementation in narrative.dialogue_rhythm (W7 package layout).

Keeps `import dialogue_rhythm` / `from dialogue_rhythm import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_rhythm as _impl

_sys.modules[__name__] = _impl
