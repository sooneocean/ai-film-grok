"""Shim — implementation in post.post_audit (W7 package layout).

Keeps `import post_audit` / `from post_audit import …` working for hard-compat.
"""
from post import post_audit as _impl
import sys as _sys

_sys.modules[__name__] = _impl
