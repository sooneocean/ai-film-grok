"""Shim — implementation in assets.wardrobe_ladder (W3 package layout).

Keeps `import wardrobe_ladder` / `from wardrobe_ladder import …` working for hard-compat.
"""

from __future__ import annotations

from assets import wardrobe_ladder as _impl
import sys as _sys

_sys.modules[__name__] = _impl
