"""Shim — implementation in post.caption_frame_audit (W7 package layout).

Keeps `import caption_frame_audit` / `from caption_frame_audit import …` working for hard-compat.
"""
import sys as _sys

from post import caption_frame_audit as _impl

_sys.modules[__name__] = _impl
