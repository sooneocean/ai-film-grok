"""Shim — implementation in spine.project_state (W3 package layout).

Keeps `import project_state` / `from project_state import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import project_state as _impl

_sys.modules[__name__] = _impl
