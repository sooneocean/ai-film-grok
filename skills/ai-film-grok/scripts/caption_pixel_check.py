"""Shim — implementation in post.caption_pixel_check (W7 package layout).

Keeps `import caption_pixel_check` / `from caption_pixel_check import …` working for hard-compat.
"""
import sys as _sys

from post import caption_pixel_check as _impl

_sys.modules[__name__] = _impl
