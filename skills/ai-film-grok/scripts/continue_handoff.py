"""Shim — implementation in spine.continue_handoff (W3 package layout).

Keeps `import continue_handoff` / `from continue_handoff import …` working for hard-compat.
"""
import sys as _sys

from spine import continue_handoff as _impl

_sys.modules[__name__] = _impl
