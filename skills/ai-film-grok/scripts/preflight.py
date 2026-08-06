"""Shim — implementation in gates.preflight (W3 package layout).

Keeps `import preflight` / `from preflight import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import preflight as _impl

_sys.modules[__name__] = _impl
