"""Shim — implementation in post.post_quality (W7 package layout).

Keeps `import post_quality` / `from post_quality import …` working for hard-compat.
"""
import sys as _sys

from post import post_quality as _impl

_sys.modules[__name__] = _impl
