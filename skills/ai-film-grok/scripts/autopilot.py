"""Shim — implementation in spine.autopilot (W3 package layout).

Keeps `import autopilot` / `from autopilot import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import autopilot as _impl

_sys.modules[__name__] = _impl
