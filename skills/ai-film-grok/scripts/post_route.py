"""Shim — implementation in post.post_route (W7 package layout).

Keeps `import post_route` / `from post_route import …` working for hard-compat.
"""
import sys as _sys

from post import post_route as _impl

_sys.modules[__name__] = _impl
