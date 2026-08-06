"""Shim — implementation in plan.production_book (W3 package layout).

Keeps `import production_book` / `from production_book import …` working for hard-compat.
"""

from __future__ import annotations

from plan import production_book as _impl
import sys as _sys

_sys.modules[__name__] = _impl
