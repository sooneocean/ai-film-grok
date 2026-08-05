"""Shim — implementation in spine.craft_spine (W3 package layout).

Keeps `import craft_spine` / `from craft_spine import …` working for hard-compat.
"""

from __future__ import annotations

from spine import craft_spine as _impl
import sys as _sys

_sys.modules[__name__] = _impl
