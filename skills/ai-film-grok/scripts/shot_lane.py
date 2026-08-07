"""Shim — implementation in media.shot_lane (W6 package layout).

Keeps `import shot_lane` / `from shot_lane import …` working for hard-compat.
"""

from media import shot_lane as _impl
from media.shot_lane import *  # noqa: F403

__all__ = list(getattr(_impl, "__all__", []))
