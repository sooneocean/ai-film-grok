"""Shim — implementation in assets.continuity_chain (W3 package layout).

Keeps `import continuity_chain` / `from continuity_chain import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import continuity_chain as _impl

_sys.modules[__name__] = _impl
