"""Shim — implementation in spine.transaction_receipt (hard-compat).

Keeps `import transaction_receipt` working after package move.
"""
from __future__ import annotations

from spine import transaction_receipt as _impl
import sys as _sys

_sys.modules[__name__] = _impl
