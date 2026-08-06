"""Shim — implementation in narrative.dialogue_production_plan (W7 package layout).

Keeps `import dialogue_production_plan` / `from dialogue_production_plan import …` working for hard-compat.
"""
from narrative import dialogue_production_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl
