"""Shim — implementation in post.render_final_music (W7 package layout).

Keeps `import render_final_music` / `from render_final_music import …` working for hard-compat.
"""
import sys as _sys

from post import render_final_music as _impl

_sys.modules[__name__] = _impl
