"""Shim — implementation in post.burn_srt_pil (W7 package layout).

Keeps `import burn_srt_pil` / `from burn_srt_pil import …` working for hard-compat.
"""
import sys as _sys

from post import burn_srt_pil as _impl

_sys.modules[__name__] = _impl
