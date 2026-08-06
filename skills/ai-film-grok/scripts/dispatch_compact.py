"""Shim — implementation in spine.dispatch_compact (W3 package layout).

Keeps `import dispatch_compact` / `from dispatch_compact import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import dispatch_compact as _impl

_sys.modules[__name__] = _impl
