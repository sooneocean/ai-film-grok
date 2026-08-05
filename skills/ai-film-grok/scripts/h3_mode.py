"""Shim — implementation in media.h3_mode (W6 package layout).

Keeps `import h3_mode` / `from h3_mode import …` working for hard-compat.
"""
from media import h3_mode as _impl
import sys as _sys

_sys.modules[__name__] = _impl
