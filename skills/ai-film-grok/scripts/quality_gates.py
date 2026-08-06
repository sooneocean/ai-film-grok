"""Shim — implementation in gates.quality_gates (W3 package layout).

Keeps `import quality_gates` / `from quality_gates import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import quality_gates as _impl

_sys.modules[__name__] = _impl
