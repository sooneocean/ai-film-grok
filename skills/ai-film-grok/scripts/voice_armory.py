"""Named, auditable local voice profiles for the private 5090 node."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Profile ids, rather than prose descriptions, are what projects lock in their
# manifests.  That keeps a character from silently changing when the default
# model changes.
VOICE_ARMORY: dict[str, dict[str, Any]] = {
    "qwen_zh_female_design": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话。",
        "label": "Qwen 自由设计中文女声",
    },
    "qwen_zh_female_vivian": {
        "kind": "tts",
        "status": "ready",
        "variant": "custom_1_7b",
        "speaker": "Vivian",
        "language": "Chinese",
        "instruction_prefix": "",
        "label": "Vivian：明亮年轻中文女声",
    },
    "qwen_zh_female_serena": {
        "kind": "tts",
        "status": "ready",
        "variant": "custom_1_7b",
        "speaker": "Serena",
        "language": "Chinese",
        "instruction_prefix": "",
        "label": "Serena：温暖柔和中文女声",
    },
    "higgs_zh_female_reference": {
        "kind": "performance",
        "status": "needs_authorized_reference",
        "label": "Higgs：授权成年中文女声参考音锁声线",
    },
    "qwen_zh_female_clone": {
        "kind": "tts",
        "status": "needs_base_model_and_authorized_reference",
        "label": "Qwen Base：授权成年中文女声参考音克隆",
    },
}


def get_voice_profile(profile_id: str) -> dict[str, Any] | None:
    """Return a copy so a render cannot mutate the source-of-truth catalog."""
    profile = VOICE_ARMORY.get(profile_id.strip())
    return dict(profile) if profile else None


def ready_tts_profile(profile_id: str) -> dict[str, Any] | None:
    profile = get_voice_profile(profile_id)
    if profile and profile.get("kind") == "tts" and profile.get("status") == "ready":
        return profile
    return None


def catalog() -> Mapping[str, dict[str, Any]]:
    return {profile_id: dict(profile) for profile_id, profile in VOICE_ARMORY.items()}
