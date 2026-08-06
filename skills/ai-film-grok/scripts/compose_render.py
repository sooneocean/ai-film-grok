"""Shim — implementation in post.compose_render (W7 package layout).

Keeps `import compose_render` / `from compose_render import …` working for hard-compat.
"""
import sys as _sys

from post import compose_render as _impl

_sys.modules[__name__] = _impl
