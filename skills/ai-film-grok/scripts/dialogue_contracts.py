"""Shim — implementation in narrative.dialogue_contracts (W7 package layout).

Keeps `import dialogue_contracts` / `from dialogue_contracts import …` working for hard-compat.
"""
from narrative import dialogue_contracts as _impl
import sys as _sys

_sys.modules[__name__] = _impl
