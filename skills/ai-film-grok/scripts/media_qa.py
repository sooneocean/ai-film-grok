"""Shim — implementation in media.media_qa (W6 package layout).

Keeps `import media_qa` / `from media_qa import …` working for hard-compat.
"""
from media import media_qa as _impl
import sys as _sys

_sys.modules[__name__] = _impl
