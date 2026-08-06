"""Shim — implementation in narrative.dialogue_contracts (W7 package layout).

Keeps `import dialogue_contracts` / `from dialogue_contracts import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_contracts as _impl

_sys.modules[__name__] = _impl
