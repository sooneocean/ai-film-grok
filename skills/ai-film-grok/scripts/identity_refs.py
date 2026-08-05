"""Shim — implementation in assets.identity_refs (W3 package layout).

Keeps `import identity_refs` / `from identity_refs import …` working for hard-compat.
"""

from __future__ import annotations

from assets import identity_refs as _impl
import sys as _sys

_sys.modules[__name__] = _impl
