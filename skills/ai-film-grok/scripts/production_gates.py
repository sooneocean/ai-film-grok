"""Shim — implementation in gates.production_gates (W3 package layout).

Keeps `import production_gates` / `from production_gates import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import production_gates as _impl

_sys.modules[__name__] = _impl
