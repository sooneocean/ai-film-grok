"""Shim — implementation in spine.autopilot (W3 package layout).

Keeps `import autopilot` / `from autopilot import …` working for hard-compat.
"""

from __future__ import annotations

from spine import autopilot as _impl
import sys as _sys

_sys.modules[__name__] = _impl
