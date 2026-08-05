"""Shim — implementation in gates.preflight (W3 package layout).

Keeps `import preflight` / `from preflight import …` working for hard-compat.
"""

from __future__ import annotations

from gates import preflight as _impl
import sys as _sys

_sys.modules[__name__] = _impl
