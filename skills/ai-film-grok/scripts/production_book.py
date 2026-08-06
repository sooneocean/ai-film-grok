"""Shim — implementation in plan.production_book (W3 package layout).

Keeps `import production_book` / `from production_book import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import production_book as _impl

_sys.modules[__name__] = _impl
