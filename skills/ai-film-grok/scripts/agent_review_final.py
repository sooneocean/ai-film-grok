"""Shim — implementation in post.agent_review_final (W7 package layout).

Keeps `import agent_review_final` / `from agent_review_final import …` working for hard-compat.
"""
from post import agent_review_final as _impl
import sys as _sys

_sys.modules[__name__] = _impl
