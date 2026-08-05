"""Shim — implementation in post.burn_srt_pil (W7 package layout).

Keeps `import burn_srt_pil` / `from burn_srt_pil import …` working for hard-compat.
"""
from post import burn_srt_pil as _impl
import sys as _sys

_sys.modules[__name__] = _impl
