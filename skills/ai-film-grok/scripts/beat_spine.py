"""Shim — implementation in plan.beat_spine (W3 package layout).

Keeps `import beat_spine` / `from beat_spine import …` working for hard-compat.
"""

from __future__ import annotations

from plan import beat_spine as _impl
import sys as _sys

_sys.modules[__name__] = _impl
