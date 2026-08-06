"""Shim — implementation in narrative.dialogue_rhythm (W7 package layout).

Keeps `import dialogue_rhythm` / `from dialogue_rhythm import …` working for hard-compat.
"""
from narrative import dialogue_rhythm as _impl
import sys as _sys

_sys.modules[__name__] = _impl
