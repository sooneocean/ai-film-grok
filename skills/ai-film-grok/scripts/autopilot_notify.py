"""Shim — implementation in spine.autopilot_notify (W3 package layout).

Keeps `import autopilot_notify` / `from autopilot_notify import …` working for hard-compat.
"""
import sys as _sys

from spine import autopilot_notify as _impl

_sys.modules[__name__] = _impl
