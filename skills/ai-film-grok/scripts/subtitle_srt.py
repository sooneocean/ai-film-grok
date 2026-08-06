"""Shim — implementation in post.subtitle_srt (W7 package layout).

Keeps `import subtitle_srt` / `from subtitle_srt import …` working for hard-compat.
"""
from post import subtitle_srt as _impl
import sys as _sys

_sys.modules[__name__] = _impl
