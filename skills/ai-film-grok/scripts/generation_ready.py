"""Shim — implementation in media.generation_ready (W6 package layout).

Keeps `import generation_ready` / `from generation_ready import …` working for hard-compat.
"""
from media import generation_ready as _impl
import sys as _sys

_sys.modules[__name__] = _impl
