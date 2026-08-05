"""Shim — implementation in post.compose_preview (W7 package layout).

Keeps `import compose_preview` / `from compose_preview import …` working for hard-compat.
"""
from post import compose_preview as _impl
import sys as _sys

_sys.modules[__name__] = _impl
