"""Shim — implementation in post.subtitle_srt (W7 package layout).

Keeps `import subtitle_srt` / `from subtitle_srt import …` working for hard-compat.
"""
import sys as _sys

from post import subtitle_srt as _impl

_sys.modules[__name__] = _impl
