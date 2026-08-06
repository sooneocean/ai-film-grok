"""Shim — implementation in plan.beat_spine (W3 package layout).

Keeps `import beat_spine` / `from beat_spine import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import beat_spine as _impl

_sys.modules[__name__] = _impl
