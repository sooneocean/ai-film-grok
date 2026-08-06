"""Shim — implementation in post.closeout (W7 package layout).

Keeps `import closeout` / `from closeout import …` working for hard-compat.
"""
import sys as _sys

from post import closeout as _impl

_sys.modules[__name__] = _impl
