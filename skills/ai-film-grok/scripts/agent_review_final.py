"""Shim — implementation in post.agent_review_final (W7 package layout).

Keeps `import agent_review_final` / `from agent_review_final import …` working for hard-compat.
"""
import sys as _sys

from post import agent_review_final as _impl

_sys.modules[__name__] = _impl
