"""Shim — implementation in media.generation_usage (W6 package layout).

Keeps `import generation_usage` / `from generation_usage import …` working for hard-compat.
"""
import sys as _sys

from media import generation_usage as _impl

_sys.modules[__name__] = _impl
