"""Shim — implementation in narrative.dialogue_production_plan (W7 package layout).

Keeps `import dialogue_production_plan` / `from dialogue_production_plan import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_production_plan as _impl

_sys.modules[__name__] = _impl
