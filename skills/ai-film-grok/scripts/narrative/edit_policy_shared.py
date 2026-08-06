"""Shared edit-policy types/constants — breaks heat ↔ policy import cycles.

Both ``edit_policy`` and ``edit_policy_heat`` import from here so heat never
needs ``sys.modules`` probing of a half-initialized edit_policy package.
"""

from __future__ import annotations


class PolicyError(ValueError):
    """Raised when an edit / heat policy input is invalid or unenforceable."""


# Act-phase pose verbs that pass Mute Frame / coitus readability (X4)
_COITUS_READABLE_MARKERS: tuple[str, ...] = (
    "straddle",
    "straddle-seat",
    "hips-sink",
    "hips sink",
    "grind",
    "grind-forward",
    "mount",
    "mount-settle",
    "pelvis",
    "pelvis-lock",
    "thrust",
    "thrust-rhythm",
    "leg-wrap",
    "leg wrap",
    "clutch",
    "arch-finish",
    "arch finish",
    "residual-tremor",
    "skin-to-skin",
    "skin to skin",
    "deep thrust",
    "deep-thrust",
    "penetrating thrust",
    "penetrating-thrust",
    "bottoming out",
    "bottoming-out",
    "internal ejaculation",
    "internal-ejaculation",
    "internal peak",
    "internal-peak",
    "overflow",
    "creampie",
    "creampie release",
    "creampie-release",
    "biological fluid",
    "biological release",
    "wet vocalization",
    "overflowing",
    "leaking",
    "残留",
    "体内",
    "高潮",
    "沉腰",
    "跨坐",
    "骑",
    "顶",
    "磨",
    "锁腰",
    "锁腿",
    "办穿",
    "吃进",
    "结合",
    "骨盆",
    "咬合",
)
# Soft poses that must NOT be the only act language
_COITUS_PSEUDO_ONLY: tuple[str, ...] = (
    "soft lean",
    "gentle hug",
    "eye contact only",
    "shoulder touch",
    "sit beside",
    "牵手",
    "对视",
    "拥抱",
    "轻靠",
)

COITUS_BEATS = frozenset(
    {
        "entry",
        "union",
        "rhythm",
        "lock",
        "finish",
        "hook",
        "undress",
        "deep_thrust",
        "internal_peak",
        "creampie_release",
    }
)
# Six-beat coverage required for hardcore / coitus_strict (undress optional extra)
# deep_thrust, internal_peak, creampie_release are extreme-intensity extensions.
COITUS_REQUIRED_BEATS = ("entry", "union", "rhythm", "lock", "finish", "hook")

__all__ = [
    "PolicyError",
    "COITUS_BEATS",
    "COITUS_REQUIRED_BEATS",
    "_COITUS_PSEUDO_ONLY",
    "_COITUS_READABLE_MARKERS",
]
