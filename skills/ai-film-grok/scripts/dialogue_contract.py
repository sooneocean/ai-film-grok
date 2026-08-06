"""Shim — implementation in narrative.dialogue_contract (W7 package layout).

Keeps `import dialogue_contract` / `from dialogue_contract import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_contract as _impl

_sys.modules[__name__] = _impl
