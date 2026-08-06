"""Shim — implementation in post.subtitle_dialogue_alignment (W7 package layout).

Keeps `import subtitle_dialogue_alignment` / `from subtitle_dialogue_alignment import …` working for hard-compat.
"""
import sys as _sys

from post import subtitle_dialogue_alignment as _impl

_sys.modules[__name__] = _impl
