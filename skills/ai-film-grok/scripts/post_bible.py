"""Shim — implementation in post.post_bible (W7 package layout).

Keeps `import post_bible` / `from post_bible import …` working for hard-compat.
"""
from post import post_bible as _impl
import sys as _sys

_sys.modules[__name__] = _impl
