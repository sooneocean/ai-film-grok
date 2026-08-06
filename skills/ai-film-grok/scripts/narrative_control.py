"""Shim — implementation in plan.narrative_control (W3 package layout).

Keeps `import narrative_control` / `from narrative_control import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import narrative_control as _impl

_sys.modules[__name__] = _impl
