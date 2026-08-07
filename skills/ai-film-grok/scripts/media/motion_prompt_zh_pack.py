"""Chinese motion prompt pack (backend-agnostic).

Canonical name for the former ``seedance_bridge`` word pack. Same pure-local
composition helpers; no Seedance network path. Prefer importing from here in
new code; ``seedance_bridge`` remains a hard-compat alias.
"""

from __future__ import annotations

try:
    from media.seedance_bridge import (  # type: ignore
        DEFAULT_NEGATIVES,
        SeedanceBridgeError,
        bridge_film_spec,
        compose_prompt,
    )
except ImportError:  # scripts/ on path
    from seedance_bridge import (  # type: ignore
        DEFAULT_NEGATIVES,
        SeedanceBridgeError,
        bridge_film_spec,
        compose_prompt,
    )

MotionPromptZhError = SeedanceBridgeError

__all__ = [
    "DEFAULT_NEGATIVES",
    "MotionPromptZhError",
    "SeedanceBridgeError",
    "bridge_film_spec",
    "compose_prompt",
]
