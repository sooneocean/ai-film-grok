"""Shim — implementation in spine.continue_handoff (W3 package layout).

Keeps `import continue_handoff` / `from continue_handoff import …` working for hard-compat.
"""
from spine import continue_handoff as _impl
import sys as _sys

_sys.modules[__name__] = _impl
