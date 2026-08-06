"""Shim — implementation in media.generation_usage (W6 package layout).

Keeps `import generation_usage` / `from generation_usage import …` working for hard-compat.
"""
from media import generation_usage as _impl
import sys as _sys

_sys.modules[__name__] = _impl
