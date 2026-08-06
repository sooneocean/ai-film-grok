"""Shim — implementation in post.post_plan (W7 package layout).

Keeps `import post_plan` / `from post_plan import …` working for hard-compat.
"""
import sys as _sys

from post import post_plan as _impl

_sys.modules[__name__] = _impl
