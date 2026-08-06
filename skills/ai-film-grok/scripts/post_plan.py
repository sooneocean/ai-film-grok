"""Shim — implementation in post.post_plan (W7 package layout).

Keeps `import post_plan` / `from post_plan import …` working for hard-compat.
"""
from post import post_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl
