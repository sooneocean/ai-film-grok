"""Shim — implementation in plan.narrative_timeline (W7 package layout).

Keeps `import narrative_timeline` / `from narrative_timeline import …` working for hard-compat.
"""
from plan import narrative_timeline as _impl
import sys as _sys

_sys.modules[__name__] = _impl
