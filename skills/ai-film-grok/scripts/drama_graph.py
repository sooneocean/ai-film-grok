"""Shim — implementation in plan.drama_graph (W3 package layout).

Keeps `import drama_graph` / `from drama_graph import …` working for hard-compat.
"""

from __future__ import annotations

from plan import drama_graph as _impl
import sys as _sys

_sys.modules[__name__] = _impl
