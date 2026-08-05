"""Shim — implementation in plan.intake (W3 package layout).

Keeps `import intake` / `from intake import …` working for hard-compat.
"""

from __future__ import annotations

from plan import intake as _impl
import sys as _sys

_sys.modules[__name__] = _impl
