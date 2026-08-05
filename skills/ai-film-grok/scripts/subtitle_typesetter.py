"""Shim — implementation in post.subtitle_typesetter (W7 package layout).

Keeps `import subtitle_typesetter` / `from subtitle_typesetter import …` working for hard-compat.
"""
from post import subtitle_typesetter as _impl
import sys as _sys

_sys.modules[__name__] = _impl
