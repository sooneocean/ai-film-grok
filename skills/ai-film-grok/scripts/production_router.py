"""Shim — implementation in plan.production_router (W3 package layout).

Keeps `import production_router` / `from production_router import …` working for hard-compat.
"""

from __future__ import annotations

from plan import production_router as _impl
import sys as _sys

_sys.modules[__name__] = _impl
