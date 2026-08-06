"""Shim — implementation in gates.cinematic_audit (W3 package layout).

Keeps `import cinematic_audit` / `from cinematic_audit import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import cinematic_audit as _impl

_sys.modules[__name__] = _impl
