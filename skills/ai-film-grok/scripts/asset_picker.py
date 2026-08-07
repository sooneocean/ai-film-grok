"""Shim — implementation in web.asset_picker."""
import sys as _sys

from web import asset_picker as _impl

_sys.modules[__name__] = _impl
