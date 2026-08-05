"""Shim — implementation in assets.continuity_chain (W3 package layout).

Keeps `import continuity_chain` / `from continuity_chain import …` working for hard-compat.
"""

from __future__ import annotations

from assets import continuity_chain as _impl
import sys as _sys

_sys.modules[__name__] = _impl
