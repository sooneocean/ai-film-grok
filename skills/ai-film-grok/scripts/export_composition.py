"""Shim — implementation in post.export_composition (W7 package layout).

Keeps `import export_composition` / `from export_composition import …` working for hard-compat.
"""
import sys as _sys

from post import export_composition as _impl

_sys.modules[__name__] = _impl
