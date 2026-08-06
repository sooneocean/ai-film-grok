"""Shim — implementation in spine.workflow_spine (W3 package layout).

Keeps `import workflow_spine` / `from workflow_spine import …` working for hard-compat.
"""

from __future__ import annotations

from spine import workflow_spine as _impl
import sys as _sys

_sys.modules[__name__] = _impl
