"""Shim — implementation in assets.clip_uniqueness (W3 package layout).

Keeps `import clip_uniqueness` / `from clip_uniqueness import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import clip_uniqueness as _impl

_sys.modules[__name__] = _impl
