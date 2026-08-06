"""Shim — implementation in spine.workflow_spine (W3 package layout).

Keeps `import workflow_spine` / `from workflow_spine import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import workflow_spine as _impl

_sys.modules[__name__] = _impl
