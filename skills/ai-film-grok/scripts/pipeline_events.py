"""Shim — implementation in spine.pipeline_events (hard-compat).

Keeps `import pipeline_events` working after package move.
"""
from __future__ import annotations

from spine import pipeline_events as _impl
import sys as _sys

_sys.modules[__name__] = _impl
