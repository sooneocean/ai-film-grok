"""Shim — implementation in assets.visual_bible (W3 package layout).

Keeps `import visual_bible` / `from visual_bible import …` working for hard-compat.
"""

from __future__ import annotations

from assets import visual_bible as _impl
import sys as _sys

_sys.modules[__name__] = _impl
