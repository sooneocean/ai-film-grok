"""Shim — implementation in post.final_editorial_review (W7 package layout).

Keeps `import final_editorial_review` / `from final_editorial_review import …` working for hard-compat.
"""
import sys as _sys

from post import final_editorial_review as _impl

_sys.modules[__name__] = _impl
