"""Dialogue style guidance: register, tone, rhythm per genre."""

from __future__ import annotations

from typing import Any

REGISTER = frozenset({"formal", "casual", "intimate", "power", "child", "elder"})
TONE = frozenset({"neutral", "warm", "cold", "sarcastic", "gentle", "sharp", "playful", "solemn"})

GENRE_RHYTHM_HINTS: dict[str, dict[str, Any]] = {
    "adult": {
        "preferred_line_length": "short (6-15 chars per turn)",
        "pause_pattern": "short-short-long (quick back-and-forth then beat)",
        "verb_style": "action verbs, physical verbs",
        "avoid": ["exposition dumps", "long philosophical monologues"],
    },
    "drama": {
        "preferred_line_length": "medium (10-25 chars per turn)",
        "pause_pattern": "medium pause between exchanges",
        "verb_style": "emotional, relational verbs",
        "avoid": ["overly casual slang", "one-word replies"],
    },
    "mystery": {
        "preferred_line_length": "short-medium (8-18 chars)",
        "pause_pattern": "deliberate pauses, trailing off",
        "verb_style": "evasive, deflective, probing",
        "avoid": ["direct answers", "emotional outbursts"],
    },
    "arthouse": {
        "preferred_line_length": "variable, poetic",
        "pause_pattern": "long pauses, fragmented",
        "verb_style": "imagistic, sensory",
        "avoid": ["exposition", "on-the-nose dialogue"],
    },
    "documentary": {
        "preferred_line_length": "medium-long (15-30 chars)",
        "pause_pattern": "steady, narrative",
        "verb_style": "factual, declarative",
        "avoid": ["dramatic exaggeration", "fictional framing"],
    },
}

# Register markers in Chinese dialogue
_REGISTER_MARKERS: dict[str, tuple[str, ...]] = {
    "formal": ("请问", "贵方", "殿下", "大人", "谨", "兹", "特此"),
    "casual": ("嘛", "啦", "哈", "呗", "撒", "呀", "呗", "哦"),
    "intimate": ("亲爱的", "宝贝", "老公", "老婆", "Darling", "宝贝儿"),
    "power": ("必须", "务必", "听好了", "给我", "让开"),
    "child": ("嘛", "呀", "嗯嗯", "不不不", "就是"),
    "elder": ("老夫", "老朽", "汝", "罢了", "且慢"),
}

# Tone markers in Chinese dialogue
_TONE_MARKERS: dict[str, tuple[str, ...]] = {
    "warm": ("好", "谢谢", "对不起", "爱你", "放心", "没关系"),
    "cold": ("无所谓", "随便", "滚", "去死", "冷血", "无情"),
    "sharp": ("哼", "够了", "闭嘴", "胡说", "荒谬", "无耻"),
    "sarcastic": ("呵呵", "是吗", "真棒", "当然", "随便你"),
    "gentle": ("轻轻", "温柔", "慢慢", "别怕", "我在"),
    "solemn": ("郑重", "誓言", "永远", "绝不", "以命相搏"),
    "playful": ("嘻嘻", "哈哈", "讨厌", "嘛嘛", "逗你玩"),
}


def detect_register(turn: dict[str, Any]) -> str:
    """Detect the social register of a dialogue turn."""
    dialogue = _text(turn.get("dialogue_zh") or turn.get("dialogue_ja") or "")
    if not dialogue:
        return "casual"
    for reg, markers in _REGISTER_MARKERS.items():
        if any(m in dialogue for m in markers):
            return reg
    return "casual"


def detect_tone(turn: dict[str, Any]) -> str:
    """Detect the emotional tone of a dialogue turn."""
    dialogue = _text(turn.get("dialogue_zh") or turn.get("dialogue_ja") or "")
    if not dialogue:
        return "neutral"
    for tone, markers in _TONE_MARKERS.items():
        if any(m in dialogue for m in markers):
            return tone
    return "neutral"


def style_guidance_for_scene(scene: dict[str, Any], genre: str = "adult") -> dict[str, Any]:
    """Return style guidance for a scene's dialogue turns."""
    rhythm = GENRE_RHYTHM_HINTS.get(genre, GENRE_RHYTHM_HINTS["adult"])
    return {
        "genre": genre,
        "register": rhythm,
        "tone_guidance": f"Maintain {genre}-appropriate tone throughout scene",
        "line_length_guidance": rhythm["preferred_line_length"],
        "pause_guidance": rhythm["pause_pattern"],
        "verb_style": rhythm["verb_style"],
        "avoid": rhythm["avoid"],
    }


def _text(value: object) -> str:
    return str(value or "").strip()
