"""Shim — implementation in media.h3_mode (W6 package layout).

Keeps `import h3_mode` / `from h3_mode import …` working for hard-compat.
"""
import sys as _sys

from media import h3_mode as _impl

_sys.modules[__name__] = _impl
