"""Shim — implementation in media.generation_request (W6 package layout).

Keeps `import generation_request` / `from generation_request import …` working for hard-compat.
"""
import sys as _sys

from media import generation_request as _impl

_sys.modules[__name__] = _impl
