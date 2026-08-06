"""Shim — implementation in narrative.dialogue_speaker_frame_gate (W7 package layout).

Keeps `import dialogue_speaker_frame_gate` / `from dialogue_speaker_frame_gate import …` working for hard-compat.
"""
from narrative import dialogue_speaker_frame_gate as _impl
import sys as _sys

_sys.modules[__name__] = _impl
