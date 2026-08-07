"""Shim — implementation in post.edit_director (W7 package layout).

Keeps `import edit_director` / `from edit_director import …` working for hard-compat.
"""
import sys as _sys

from post import edit_director as _impl

_sys.modules[__name__] = _impl
