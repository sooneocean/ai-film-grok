"""Shim — implementation in narrative.dialogue_competition (W7 package layout).

Keeps `import dialogue_competition` / `from dialogue_competition import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_competition as _impl

_sys.modules[__name__] = _impl
