"""Shim — implementation in assets.style_lock (W3 package layout).

Keeps `import style_lock` / `from style_lock import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import style_lock as _impl

_sys.modules[__name__] = _impl
