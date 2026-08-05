"""Shim — implementation in media.i2v_provider (W6 package layout).

Keeps `import i2v_provider` / `from i2v_provider import …` working for hard-compat.
"""
from media import i2v_provider as _impl
import sys as _sys

_sys.modules[__name__] = _impl
