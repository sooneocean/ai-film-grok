"""Shim — implementation in assets.performance_state (W3 package layout).

Keeps `import performance_state` / `from performance_state import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import performance_state as _impl

_sys.modules[__name__] = _impl
