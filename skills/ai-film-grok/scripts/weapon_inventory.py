"""Shim — implementation in media.weapon_inventory (W6 package layout).

Keeps `import weapon_inventory` / `from weapon_inventory import …` working for hard-compat.
"""
from media import weapon_inventory as _impl
import sys as _sys

_sys.modules[__name__] = _impl
