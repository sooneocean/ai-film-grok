"""Shim — implementation in spine.craft_spine (W3 package layout).

Keeps `import craft_spine` / `from craft_spine import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import craft_spine as _impl

_sys.modules[__name__] = _impl
