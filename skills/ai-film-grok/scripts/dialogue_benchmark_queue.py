"""Shim — implementation in narrative.dialogue_benchmark_queue (W7 package layout).

Keeps `import dialogue_benchmark_queue` / `from dialogue_benchmark_queue import …` working for hard-compat.
"""
from narrative import dialogue_benchmark_queue as _impl
import sys as _sys

_sys.modules[__name__] = _impl
