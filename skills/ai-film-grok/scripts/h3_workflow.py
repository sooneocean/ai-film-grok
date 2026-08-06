"""Shim — implementation in media.h3_workflow (W6 package layout).

Keeps `import h3_workflow` / `from h3_workflow import …` working for hard-compat.
"""
from media import h3_workflow as _impl
import sys as _sys

_sys.modules[__name__] = _impl
