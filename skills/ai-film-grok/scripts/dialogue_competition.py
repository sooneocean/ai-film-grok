"""Shim — implementation in narrative.dialogue_competition (W7 package layout).

Keeps `import dialogue_competition` / `from dialogue_competition import …` working for hard-compat.
"""
from narrative import dialogue_competition as _impl
import sys as _sys

_sys.modules[__name__] = _impl
