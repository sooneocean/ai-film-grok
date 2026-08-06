"""Shim — implementation in media.h3_media_pack (W6 package layout).

Keeps `import h3_media_pack` / `from h3_media_pack import …` working for hard-compat.
"""
import sys as _sys

from media import h3_media_pack as _impl

_sys.modules[__name__] = _impl
