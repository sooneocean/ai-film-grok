"""Shim — implementation in post.render_final (W4)."""
from post import render_final as _impl
import sys as _sys
_sys.modules[__name__] = _impl
