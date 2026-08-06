"""Shim — implementation in plan.production_router (W3 package layout).

Keeps `import production_router` / `from production_router import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import production_router as _impl

_sys.modules[__name__] = _impl
