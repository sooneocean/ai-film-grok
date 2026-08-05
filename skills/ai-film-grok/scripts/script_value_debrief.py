"""Shim — implementation in plan.script_value_debrief (W3 package layout).

Keeps `import script_value_debrief` / `from script_value_debrief import …` working for hard-compat.
"""

from __future__ import annotations

from plan import script_value_debrief as _impl
import sys as _sys

_sys.modules[__name__] = _impl
