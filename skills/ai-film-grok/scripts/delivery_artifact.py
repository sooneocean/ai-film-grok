"""Shim — implementation in gates.delivery_artifact (W3 package layout).

Keeps `import delivery_artifact` / `from delivery_artifact import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import delivery_artifact as _impl

_sys.modules[__name__] = _impl
