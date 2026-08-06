"""Shim — implementation in post.render_final_music (W7 package layout).

Keeps `import render_final_music` / `from render_final_music import …` working for hard-compat.
"""
from post import render_final_music as _impl
import sys as _sys

_sys.modules[__name__] = _impl
