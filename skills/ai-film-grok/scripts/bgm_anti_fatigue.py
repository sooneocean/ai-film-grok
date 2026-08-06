"""Shim — implementation in audio.bgm_anti_fatigue."""
import sys as _sys

from audio import bgm_anti_fatigue as _impl

_sys.modules[__name__] = _impl
