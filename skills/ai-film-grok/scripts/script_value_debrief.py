"""Shim — implementation in plan.script_value_debrief (W3 package layout).

Keeps `import script_value_debrief` / `from script_value_debrief import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import script_value_debrief as _impl

_sys.modules[__name__] = _impl
