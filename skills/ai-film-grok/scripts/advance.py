"""Shim — implementation in spine.advance (W3 package layout).

Keeps `import advance` / `from advance import …` working for hard-compat.
"""

from __future__ import annotations

from spine import advance as _impl
import sys as _sys

_sys.modules[__name__] = _impl
