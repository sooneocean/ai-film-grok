"""Shim — implementation in gates.gate_auto (W3 package layout).

Keeps `import gate_auto` / `from gate_auto import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import gate_auto as _impl

_sys.modules[__name__] = _impl
