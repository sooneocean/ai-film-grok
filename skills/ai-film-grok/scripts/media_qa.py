"""Shim — implementation in media.media_qa (W6 package layout).

Keeps `import media_qa` / `from media_qa import …` working for hard-compat.
"""
import sys as _sys

from media import media_qa as _impl

_sys.modules[__name__] = _impl
