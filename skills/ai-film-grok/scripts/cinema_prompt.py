"""Shim — implementation in narrative.cinema_prompt (W7 package layout).

Keeps `import cinema_prompt` / `from cinema_prompt import …` working for hard-compat.
"""
from narrative import cinema_prompt as _impl
import sys as _sys

_sys.modules[__name__] = _impl
