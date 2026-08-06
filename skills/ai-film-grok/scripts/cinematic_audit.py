"""Shim — implementation in gates.cinematic_audit (W3 package layout).

Keeps `import cinematic_audit` / `from cinematic_audit import …` working for hard-compat.
"""

from __future__ import annotations

from gates import cinematic_audit as _impl
import sys as _sys

_sys.modules[__name__] = _impl
