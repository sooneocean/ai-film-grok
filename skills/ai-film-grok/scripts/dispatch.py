"""Shim — implementation in spine.dispatch (W3 package layout).

Keeps `import dispatch` / `from dispatch import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import dispatch as _impl

_sys.modules[__name__] = _impl
