"""Shim — implementation in narrative.dialogue_speaker_frame_gate (W7 package layout).

Keeps `import dialogue_speaker_frame_gate` / `from dialogue_speaker_frame_gate import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_speaker_frame_gate as _impl

_sys.modules[__name__] = _impl
