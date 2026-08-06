"""Shim — implementation in post.post_audit (W7 package layout).

Keeps `import post_audit` / `from post_audit import …` working for hard-compat.
"""
import sys as _sys

from post import post_audit as _impl

_sys.modules[__name__] = _impl
