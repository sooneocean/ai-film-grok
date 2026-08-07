"""Shim — implementation in post.local_omni_review (hard-compat).

Keeps `import local_omni_review` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import local_omni_review as _impl

_sys.modules[__name__] = _impl
