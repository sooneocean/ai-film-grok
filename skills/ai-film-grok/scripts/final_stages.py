"""Shim — implementation in post.final_stages (W7 package layout).

Keeps `import final_stages` / `from final_stages import …` working for hard-compat.
"""
import sys as _sys

from post import final_stages as _impl

_sys.modules[__name__] = _impl
