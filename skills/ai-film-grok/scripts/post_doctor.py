"""Shim — implementation in post.post_doctor (W7 package layout).

Keeps `import post_doctor` / `from post_doctor import …` working for hard-compat.
"""
import sys as _sys

from post import post_doctor as _impl

_sys.modules[__name__] = _impl
