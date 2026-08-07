"""Shim — implementation in web.onboarding."""
import sys as _sys

from web import onboarding as _impl

_sys.modules[__name__] = _impl
