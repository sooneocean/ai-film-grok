"""Shim — implementation in assets.anatomy_safety (W3 package layout).

Keeps `import anatomy_safety` / `from anatomy_safety import …` working for hard-compat.
"""

from __future__ import annotations

from assets import anatomy_safety as _impl
import sys as _sys

_sys.modules[__name__] = _impl
