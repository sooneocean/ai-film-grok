"""Shim — implementation in assets.clip_uniqueness (W3 package layout).

Keeps `import clip_uniqueness` / `from clip_uniqueness import …` working for hard-compat.
"""

from __future__ import annotations

from assets import clip_uniqueness as _impl
import sys as _sys

_sys.modules[__name__] = _impl
