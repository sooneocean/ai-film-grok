"""Shim — implementation in gates.delivery_package (W3 package layout).

Keeps `import delivery_package` / `from delivery_package import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import delivery_package as _impl

_sys.modules[__name__] = _impl
