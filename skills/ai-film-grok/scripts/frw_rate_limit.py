"""Shim — implementation in media.frw_rate_limit (W6 package layout).

Keeps `import frw_rate_limit` / `from frw_rate_limit import …` working for hard-compat.
"""
from media import frw_rate_limit as _impl
import sys as _sys

_sys.modules[__name__] = _impl
