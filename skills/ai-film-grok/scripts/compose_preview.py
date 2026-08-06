"""Shim — implementation in post.compose_preview (W7 package layout).

Keeps `import compose_preview` / `from compose_preview import …` working for hard-compat.
"""
import sys as _sys

from post import compose_preview as _impl

_sys.modules[__name__] = _impl
