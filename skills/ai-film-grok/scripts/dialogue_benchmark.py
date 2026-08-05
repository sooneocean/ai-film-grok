"""Shim — implementation in narrative.dialogue_benchmark (W7 package layout).

Keeps `import dialogue_benchmark` / `from dialogue_benchmark import …` working for hard-compat.
"""
from narrative import dialogue_benchmark as _impl
import sys as _sys

_sys.modules[__name__] = _impl
