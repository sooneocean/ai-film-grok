"""Shim — implementation in plan.narrative_control (W3 package layout).

Keeps `import narrative_control` / `from narrative_control import …` working for hard-compat.
"""

from __future__ import annotations

from plan import narrative_control as _impl
import sys as _sys

_sys.modules[__name__] = _impl
