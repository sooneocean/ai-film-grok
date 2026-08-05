"""Shim — implementation in media.generation_request (W6 package layout).

Keeps `import generation_request` / `from generation_request import …` working for hard-compat.
"""
from media import generation_request as _impl
import sys as _sys

_sys.modules[__name__] = _impl
