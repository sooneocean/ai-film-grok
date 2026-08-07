"""Shim — implementation in spine.pipeline_events (hard-compat).

Keeps `import pipeline_events` working after package move.
"""
from __future__ import annotations

import sys as _sys

from spine import pipeline_events as _impl

_sys.modules[__name__] = _impl
