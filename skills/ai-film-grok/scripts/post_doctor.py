"""Shim — implementation in post.post_doctor (W7 package layout).

Keeps `import post_doctor` / `from post_doctor import …` working for hard-compat.
"""
from post import post_doctor as _impl
import sys as _sys

_sys.modules[__name__] = _impl
