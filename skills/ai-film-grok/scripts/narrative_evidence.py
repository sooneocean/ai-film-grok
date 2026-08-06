"""Shim — implementation in plan.narrative_evidence (W7 package layout).

Keeps `import narrative_evidence` / `from narrative_evidence import …` working for hard-compat.
"""
from plan import narrative_evidence as _impl
import sys as _sys

_sys.modules[__name__] = _impl
