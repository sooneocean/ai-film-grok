"""Shim — implementation in plan.shot_planning (W3 package layout).

Keeps `import shot_planning` / `from shot_planning import …` working for hard-compat.
"""

from __future__ import annotations

from plan import shot_planning as _impl
import sys as _sys

_sys.modules[__name__] = _impl
