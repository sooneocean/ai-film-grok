"""Shim — implementation in assets.continuity (W3 package layout).

Keeps `import continuity` / `from continuity import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import continuity as _impl

_sys.modules[__name__] = _impl
