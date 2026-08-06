"""Shim — implementation in plan.drama_graph (W3 package layout).

Keeps `import drama_graph` / `from drama_graph import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from plan import drama_graph as _impl

_sys.modules[__name__] = _impl
