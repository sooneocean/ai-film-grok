"""Shim — implementation in media.h3_media_pack (W6 package layout).

Keeps `import h3_media_pack` / `from h3_media_pack import …` working for hard-compat.
"""
from media import h3_media_pack as _impl
import sys as _sys

_sys.modules[__name__] = _impl
