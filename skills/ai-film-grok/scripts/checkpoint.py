"""Shim — implementation in spine.checkpoint (W3 package layout).

Keeps `import checkpoint` / `from checkpoint import …` working for hard-compat.
"""
import sys as _sys

from spine import checkpoint as _impl

_sys.modules[__name__] = _impl
