"""Shim — implementation in assets.asset_registry (W3 package layout).

Keeps `import asset_registry` / `from asset_registry import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import asset_registry as _impl

_sys.modules[__name__] = _impl
