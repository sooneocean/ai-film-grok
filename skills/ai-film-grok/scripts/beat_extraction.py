"""Shim — implementation in plan.beat_extraction (W3 package layout).

Keeps `import beat_extraction` / `from beat_extraction import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import beat_extraction as _impl

_sys.modules[__name__] = _impl
