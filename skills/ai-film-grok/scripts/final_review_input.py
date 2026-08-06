"""Shim — implementation in post.final_review_input (W7 package layout).

Keeps `import final_review_input` / `from final_review_input import …` working for hard-compat.
"""
import sys as _sys

from post import final_review_input as _impl

_sys.modules[__name__] = _impl
