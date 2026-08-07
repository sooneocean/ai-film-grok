"""Shim — implementation in post.review_mode_policy (hard-compat)."""
from __future__ import annotations

import sys as _sys

from post import review_mode_policy as _impl

_sys.modules[__name__] = _impl
