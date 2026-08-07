"""Shim — implementation in plan.shot_card (Film Production OS W2)."""
import sys as _sys

from plan import shot_card as _impl

_sys.modules[__name__] = _impl
