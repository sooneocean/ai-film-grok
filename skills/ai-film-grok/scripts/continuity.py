"""Shim — implementation in assets.continuity (W3 package layout).

Keeps `import continuity` / `from continuity import …` working for hard-compat.
"""

from __future__ import annotations

from assets import continuity as _impl
import sys as _sys

_sys.modules[__name__] = _impl
