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
    "qwen_zh_female_gentle": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，温柔、温暖、自然。",
        "label": "设计女声：温柔暖声（非固定角色）",
    },
    "qwen_zh_female_mature": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，成熟、沉稳、低中音。",
        "label": "设计女声：成熟沉稳（非固定角色）",
    },
    "qwen_zh_female_cool": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，清冷、克制、吐字清晰。",
        "label": "设计女声：清冷克制（非固定角色）",
    },
    "qwen_zh_female_lively": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，明亮、活泼、有亲和力。",
        "label": "设计女声：明亮活泼（非固定角色）",
    },
    "qwen_zh_female_breathy": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，轻微气声、亲近但清晰。",
        "label": "设计女声：轻气声（非固定角色）",
    },
    "qwen_zh_female_narrator": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，叙述感稳定、自然、清晰。",
        "label": "设计女声：稳定旁白（非固定角色）",
    },
    "qwen_zh_female_vivian": {
        "kind": "tts",
        "status": "requires_node_variant",
        "variant": "custom_1_7b",
        "speaker": "Vivian",
        "language": "Chinese",
        "instruction_prefix": "",
        "label": "Vivian：明亮年轻中文女声",
    },
    "qwen_zh_female_serena": {
        "kind": "tts",
        "status": "requires_node_variant",
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
    if (
        profile
        and profile.get("kind") == "tts"
        and profile.get("status")
        in {
            "ready",
            "requires_node_variant",
        }
    ):
        return profile
    return None


def render_ready_tts_profile(
    profile_id: str, available_variants: Mapping[str, object]
) -> dict[str, Any]:
    """Resolve one catalogued voice only when its node variant is live."""
    resolved_id = profile_id.strip() or "qwen_zh_female_design"
    profile = get_voice_profile(resolved_id)
    if profile is None:
        raise ValueError(f"unknown voice profile: {resolved_id}")
    if ready_tts_profile(resolved_id) is None:
        raise ValueError(f"voice profile is not render-ready: {resolved_id}")
    variant = str(profile.get("variant") or "")
    if available_variants.get(variant) is not True:
        raise ValueError(f"voice model variant is unavailable: {variant}")
    return profile


def catalog() -> Mapping[str, dict[str, Any]]:
    return {profile_id: dict(profile) for profile_id, profile in VOICE_ARMORY.items()}
