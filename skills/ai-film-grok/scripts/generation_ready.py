"""Shim — implementation in media.generation_ready (W6 package layout).

Keeps `import generation_ready` / `from generation_ready import …` working for hard-compat.
"""
import sys as _sys

from media import generation_ready as _impl

_sys.modules[__name__] = _impl
