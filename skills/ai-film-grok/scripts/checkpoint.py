"""Shim — implementation in spine.checkpoint (W3 package layout).

Keeps `import checkpoint` / `from checkpoint import …` working for hard-compat.
"""
from spine import checkpoint as _impl
import sys as _sys

_sys.modules[__name__] = _impl
