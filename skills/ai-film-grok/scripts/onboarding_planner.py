"""Shim — implementation in web.onboarding_planner."""
import sys as _sys

from web import onboarding_planner as _impl

_sys.modules[__name__] = _impl
