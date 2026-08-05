"""Shim — implementation in media.comfy_video (W6 package layout).

Keeps `import comfy_video` / `from comfy_video import …` working for hard-compat.
"""
from media import comfy_video as _impl
import sys as _sys

_sys.modules[__name__] = _impl
