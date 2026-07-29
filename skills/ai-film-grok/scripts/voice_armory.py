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
    "qwen_zh_female_elegant": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，优雅、从容、音色细腻。",
        "label": "设计女声：优雅从容（非固定角色）",
    },
    "qwen_zh_female_husky": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，微微沙哑、成熟、吐字清晰。",
        "label": "设计女声：微沙哑成熟（非固定角色）",
    },
    "qwen_zh_female_whisper": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，低声轻语、近距离、清晰可懂。",
        "label": "设计女声：低声轻语（非固定角色）",
    },
    "qwen_zh_female_playful": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，俏皮、灵动、带自然笑意。",
        "label": "设计女声：俏皮灵动（非固定角色）",
    },
    "qwen_zh_female_confident": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，自信、利落、有掌控感。",
        "label": "设计女声：自信利落（非固定角色）",
    },
    "qwen_zh_female_comforting": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，安抚、柔和、可信赖。",
        "label": "设计女声：安抚治愈（非固定角色）",
    },
    "qwen_zh_female_melancholy": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，淡淡忧郁、克制、气息平稳。",
        "label": "设计女声：淡淡忧郁（非固定角色）",
    },
    "qwen_zh_female_mysterious": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，神秘、安静、音色偏低。",
        "label": "设计女声：神秘低声（非固定角色）",
    },
    "qwen_zh_female_documentary": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，纪录片旁白感、稳定、客观。",
        "label": "设计女声：纪录片旁白（非固定角色）",
    },
    "qwen_zh_female_storyteller": {
        "kind": "tts",
        "status": "ready",
        "variant": "voice_design",
        "speaker": "",
        "language": "Chinese",
        "instruction_prefix": "成年中文女声，标准普通话，讲故事感强、画面感自然、节奏舒缓。",
        "label": "设计女声：故事讲述（非固定角色）",
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
    "qwen_zh_female_vivian_fast": {
        "kind": "tts",
        "status": "requires_node_variant",
        "variant": "custom_0_6b",
        "speaker": "Vivian",
        "language": "Chinese",
        "instruction_prefix": "",
        "label": "Vivian 快速版：明亮年轻中文女声",
    },
    "qwen_zh_female_serena_fast": {
        "kind": "tts",
        "status": "requires_node_variant",
        "variant": "custom_0_6b",
        "speaker": "Serena",
        "language": "Chinese",
        "instruction_prefix": "",
        "label": "Serena 快速版：温暖柔和中文女声",
    },
    "qwen_ja_female_ono_anna": {
        "kind": "tts",
        "status": "requires_node_variant",
        "variant": "custom_0_6b",
        "speaker": "Ono_Anna",
        "language": "Japanese",
        "instruction_prefix": "",
        "label": "Ono_Anna：轻快日文女声",
    },
    "qwen_ko_female_sohee": {
        "kind": "tts",
        "status": "requires_node_variant",
        "variant": "custom_0_6b",
        "speaker": "Sohee",
        "language": "Korean",
        "instruction_prefix": "",
        "label": "Sohee：温暖韩文女声",
    },
    "higgs_zh_female_reference": {
        "kind": "performance",
        "status": "needs_authorized_reference",
        "label": "Higgs：授权成年中文女声参考音锁声线",
    },
    "qwen_zh_female_clone": {
        "kind": "tts",
        "status": "needs_authorized_reference",
        "label": "Qwen Base：已备好模型，等待授权成年中文女声参考音克隆",
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
