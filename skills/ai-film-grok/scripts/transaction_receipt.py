"""Shim — implementation in spine.transaction_receipt (hard-compat).

Keeps `import transaction_receipt` working after package move.
"""
from __future__ import annotations

import sys as _sys

from spine import transaction_receipt as _impl

_sys.modules[__name__] = _impl
