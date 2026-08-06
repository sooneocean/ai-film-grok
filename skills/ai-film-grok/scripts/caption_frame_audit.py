"""Shim — implementation in post.caption_frame_audit (W7 package layout).

Keeps `import caption_frame_audit` / `from caption_frame_audit import …` working for hard-compat.
"""
from post import caption_frame_audit as _impl
import sys as _sys

_sys.modules[__name__] = _impl
