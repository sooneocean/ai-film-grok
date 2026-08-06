"""Shim — implementation in post.final_editorial_review (W7 package layout).

Keeps `import final_editorial_review` / `from final_editorial_review import …` working for hard-compat.
"""
from post import final_editorial_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl
