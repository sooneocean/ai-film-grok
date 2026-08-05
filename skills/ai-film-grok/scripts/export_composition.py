"""Shim — implementation in post.export_composition (W7 package layout).

Keeps `import export_composition` / `from export_composition import …` working for hard-compat.
"""
from post import export_composition as _impl
import sys as _sys

_sys.modules[__name__] = _impl
