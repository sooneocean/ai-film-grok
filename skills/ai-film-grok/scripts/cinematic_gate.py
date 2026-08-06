"""Shim — implementation in gates.cinematic_gate (W3 package layout).

Keeps `import cinematic_gate` / `from cinematic_gate import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import cinematic_gate as _impl

_sys.modules[__name__] = _impl
