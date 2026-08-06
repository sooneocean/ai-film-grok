"""Shim — implementation in post.post_bible (W7 package layout).

Keeps `import post_bible` / `from post_bible import …` working for hard-compat.
"""
import sys as _sys

from post import post_bible as _impl

_sys.modules[__name__] = _impl
