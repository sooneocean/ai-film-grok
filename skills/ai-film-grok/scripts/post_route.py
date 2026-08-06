"""Shim — implementation in post.post_route (W7 package layout).

Keeps `import post_route` / `from post_route import …` working for hard-compat.
"""
from post import post_route as _impl
import sys as _sys

_sys.modules[__name__] = _impl
