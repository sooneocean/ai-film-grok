"""Shim — implementation in post.final_stages (W7 package layout).

Keeps `import final_stages` / `from final_stages import …` working for hard-compat.
"""
from post import final_stages as _impl
import sys as _sys

_sys.modules[__name__] = _impl
