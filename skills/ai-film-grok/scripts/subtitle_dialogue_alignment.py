"""Shim — implementation in post.subtitle_dialogue_alignment (W7 package layout).

Keeps `import subtitle_dialogue_alignment` / `from subtitle_dialogue_alignment import …` working for hard-compat.
"""
from post import subtitle_dialogue_alignment as _impl
import sys as _sys

_sys.modules[__name__] = _impl
