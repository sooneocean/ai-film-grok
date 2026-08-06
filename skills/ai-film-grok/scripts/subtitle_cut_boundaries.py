"""Shim — implementation in post.subtitle_cut_boundaries (W7 package layout).

Keeps `import subtitle_cut_boundaries` / `from subtitle_cut_boundaries import …` working for hard-compat.
"""
from post import subtitle_cut_boundaries as _impl
import sys as _sys

_sys.modules[__name__] = _impl
