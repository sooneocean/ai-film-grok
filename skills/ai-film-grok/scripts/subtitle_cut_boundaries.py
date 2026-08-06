"""Shim — implementation in post.subtitle_cut_boundaries (W7 package layout).

Keeps `import subtitle_cut_boundaries` / `from subtitle_cut_boundaries import …` working for hard-compat.
"""
import sys as _sys

from post import subtitle_cut_boundaries as _impl

_sys.modules[__name__] = _impl
