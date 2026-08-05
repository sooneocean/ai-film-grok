"""Shim — implementation in media.frw_upload (W6 package layout).

Keeps `import frw_upload` / `from frw_upload import …` working for hard-compat.
"""
from media import frw_upload as _impl
import sys as _sys

_sys.modules[__name__] = _impl
