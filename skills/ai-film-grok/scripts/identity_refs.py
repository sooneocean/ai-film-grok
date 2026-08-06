"""Shim — implementation in assets.identity_refs (W3 package layout).

Keeps `import identity_refs` / `from identity_refs import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import identity_refs as _impl

_sys.modules[__name__] = _impl
