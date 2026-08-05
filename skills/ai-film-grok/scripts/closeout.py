"""Shim — implementation in post.closeout (W7 package layout).

Keeps `import closeout` / `from closeout import …` working for hard-compat.
"""
from post import closeout as _impl
import sys as _sys

_sys.modules[__name__] = _impl
