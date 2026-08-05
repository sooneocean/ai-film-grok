"""Shim — implementation in post.post_quality (W7 package layout).

Keeps `import post_quality` / `from post_quality import …` working for hard-compat.
"""
from post import post_quality as _impl
import sys as _sys

_sys.modules[__name__] = _impl
