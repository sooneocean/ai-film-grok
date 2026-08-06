"""Shim — implementation in gates.approval_ledger (W3 package layout).

Keeps `import approval_ledger` / `from approval_ledger import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import approval_ledger as _impl

_sys.modules[__name__] = _impl
