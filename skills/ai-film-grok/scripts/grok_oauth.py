"""Shim — implementation in media.grok_oauth (W6 package layout).

Keeps `import grok_oauth` / `from grok_oauth import …` working for hard-compat.
"""
from media import grok_oauth as _impl
import sys as _sys

_sys.modules[__name__] = _impl
