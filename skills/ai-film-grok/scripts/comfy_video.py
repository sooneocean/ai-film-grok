"""Shim — implementation in media.comfy_video (W6 package layout).

Keeps `import comfy_video` / `from comfy_video import …` working for hard-compat.
"""
import sys as _sys

from media import comfy_video as _impl

_sys.modules[__name__] = _impl
