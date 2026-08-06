"""Shim — implementation in assets.still_uniqueness (W3 package layout).

Keeps `import still_uniqueness` / `from still_uniqueness import …` working for hard-compat.
"""

from __future__ import annotations

from assets import still_uniqueness as _impl
import sys as _sys

_sys.modules[__name__] = _impl
