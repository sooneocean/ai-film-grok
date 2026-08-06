"""Shim — implementation in media.frw_upload (W6 package layout).

Keeps `import frw_upload` / `from frw_upload import …` working for hard-compat.
"""
import sys as _sys

from media import frw_upload as _impl

_sys.modules[__name__] = _impl
