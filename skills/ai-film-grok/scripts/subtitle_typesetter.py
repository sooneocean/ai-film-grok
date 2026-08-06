"""Shim — implementation in post.subtitle_typesetter (W7 package layout).

Keeps `import subtitle_typesetter` / `from subtitle_typesetter import …` working for hard-compat.
"""
import sys as _sys

from post import subtitle_typesetter as _impl

_sys.modules[__name__] = _impl
