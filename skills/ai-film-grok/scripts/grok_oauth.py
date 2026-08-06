"""Shim — implementation in media.grok_oauth (W6 package layout).

Keeps `import grok_oauth` / `from grok_oauth import …` working for hard-compat.
"""
import sys as _sys

from media import grok_oauth as _impl

_sys.modules[__name__] = _impl
