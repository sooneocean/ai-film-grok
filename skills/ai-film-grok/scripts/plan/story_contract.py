"""Story contract authoring guide — suggest protagonist goal, opposition, stakes, climax, ending hook."""

from __future__ import annotations

import copy
from typing import Any

# Genre-specific story templates used to suggest contract fields.
# Each template provides a plausible narrative arc derived from genre + logline.
GENRE_CONTRACT_TEMPLATES: dict[str, dict[str, str]] = {
    "adult": {
        "theme": "欲望与边界",
        "protagonist_goal": "主角渴望在今夜得到对方",
        "protagonist_want": "占有与亲密",
        "protagonist_need": "被看见、被渴望",
        "protagonist_arc": "从克制到释放",
        "opposition": "社会规范与自我设限",
        "stakes": "若今夜不成，全世界都不会知道",
        "climax_choice": "选择彻底交出自己",
        "ending_hook": "清晨醒来，一切是否真实",
    },
    "drama": {
        "theme": "关系与选择",
        "protagonist_goal": "主角想要修复或结束一段关系",
        "protagonist_want": "被理解",
        "protagonist_need": "面对真相",
        "protagonist_arc": "从逃避到承担",
        "opposition": "彼此的不信任与旧伤",
        "stakes": "若不说出真相，关系将永远停滞",
        "climax_choice": "选择坦白或继续沉默",
        "ending_hook": "对方能否接受这个真相",
    },
    "mystery": {
        "theme": "真相与代价",
        "protagonist_goal": "主角想要揭开隐藏的秘密",
        "protagonist_want": "正义或答案",
        "protagonist_need": "面对真相背后的危险",
        "protagonist_arc": "从无知到警觉",
        "opposition": "隐瞒真相的人与力量",
        "stakes": "若真相被掩埋，下一个受害者将是",
        "climax_choice": "选择公开真相或保护自己",
        "ending_hook": "真相之后，新的谜题浮现",
    },
    "arthouse": {
        "theme": "存在与意义",
        "protagonist_goal": "主角想要找到存在的理由",
        "protagonist_want": "归属感",
        "protagonist_need": "与自我和解",
        "protagonist_arc": "从迷失到觉醒",
        "opposition": "内心的空虚与外在的疏离",
        "stakes": "若继续迷失，将永远无法触及真实",
        "climax_choice": "选择留下或离开",
        "ending_hook": "选择之后，路在何方",
    },
    "documentary": {
        "theme": "记录与见证",
        "protagonist_goal": "主角想要呈现真实",
        "protagonist_want": "被看见、被听见",
        "protagonist_need": "面对镜头背后的勇气",
        "protagonist_arc": "从旁观者到参与者",
        "opposition": "权力的压制与遗忘",
        "stakes": "若不被记录，这段历史将消失",
        "climax_choice": "选择曝光或沉默",
        "ending_hook": "影像之后，世界是否改变",
    },
}

# Default fallback when genre is unknown or not in templates.
DEFAULT_CONTRACT: dict[str, str] = GENRE_CONTRACT_TEMPLATES["adult"]

# Keywords that suggest a more specific emotional arc.
# Keys use "from|to" delimiter so split("|") yields clean parts.
_EMOTIONAL_ARC_KEYWORDS: dict[str, list[str]] = {
    "fear|courage": ["恐惧", "害怕", "怯", "畏"],
    "anger|acceptance": ["愤怒", "生气", "怨恨", "释怀", "接受"],
    "desire|sacrifice": ["欲望", "渴望", "牺牲", "放手", "成全"],
    "isolation|connection": ["孤独", "孤立", "连接", "靠近", "温暖"],
    "confusion|clarity": ["困惑", "迷茫", "清醒", "明白", "顿悟"],
    "resistance|surrender": ["抵抗", "抗拒", "屈服", "放下", "接纳"],
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _extract_emotional_arc(normalized: dict[str, Any]) -> list[str]:
    """Suggest an emotional arc based on genre and plot point markers."""
    genre = _text(normalized.get("genre") or "adult")
    raw = _text(normalized.get("raw_excerpt") or normalized.get("logline") or "")
    low = raw.lower()

    arc: list[str] = []
    for arc_name, keywords in _EMOTIONAL_ARC_KEYWORDS.items():
        for kw in keywords:
            if kw in low or kw in raw:
                parts = arc_name.split("|")
                if len(parts) == 2:
                    from_part, to_part = parts
                    if from_part not in arc:
                        arc.append(from_part)
                    if to_part not in arc:
                        arc.append(to_part)
                break

    # Fallback: at least 3 beats for a valid arc
    if len(arc) < 3:
        if genre == "adult":
            arc = ["克制", "渴望", "释放"]
        elif genre == "mystery":
            arc = ["无知", "警觉", "真相"]
        elif genre == "drama":
            arc = ["逃避", "冲突", "承担"]
        else:
            arc = ["迷失", "挣扎", "觉醒"]

    return arc[:5]


def draft_story_contract(normalized: dict[str, Any]) -> dict[str, Any]:
    """Create an honest story contract; unknown intent stays blank/draft.

    Genre suggestions from ``suggest_story_contract`` are pre-filled as
    ``draft_suggested`` so the author can review and confirm. Optional
    ``story_contract_seed`` on the normalized payload overrides fields.
    """
    logline = str(normalized.get("logline") or "")
    genre = str(normalized.get("genre") or "adult")
    contract: dict[str, Any] = {
        "genre": genre,
        "premise": logline,
        "logline": logline,
        "theme": "",
        "protagonist_ids": [
            str(c.get("id"))
            for c in (normalized.get("character_candidates") or [])
            if isinstance(c, dict) and c.get("id")
        ][:2],
        "protagonist_goal": "",
        "protagonist_want": "",
        "protagonist_need": "",
        "protagonist_arc": "",
        "opposition": "",
        "stakes": "",
        "climax_choice": "",
        "ending_hook": "",
        "emotional_arc": [],
        "act_structure": {
            "setup": "",
            "confrontation": "",
            "resolution": "",
            "setup_ratio": 0.20,
            "confrontation_ratio": 0.50,
            "resolution_ratio": 0.30,
        },
        "pace_chart": [],
        "constraints": [],
        "status": "needs_authoring",
        "authoring_questions": [
            "主角想要什么？",
            "谁或什么阻止他？",
            "失败的代价是什么？",
            "本集的关键选择是什么？",
            "结尾留下什么未解决问题？",
        ],
    }
    suggestions = suggest_story_contract(normalized)
    for key in (
        "theme",
        "protagonist_goal",
        "protagonist_want",
        "protagonist_need",
        "protagonist_arc",
        "opposition",
        "stakes",
        "climax_choice",
        "ending_hook",
        "emotional_arc",
        "act_structure",
    ):
        val = suggestions.get(key)
        if val not in (None, "", [], {}):
            contract[key] = copy.deepcopy(val)
    if suggestions.get("status") == "draft_suggested":
        contract["status"] = "draft_suggested"
        contract["authoring_questions"] = (
            suggestions.get("authoring_questions") or contract["authoring_questions"]
        )
    seed = normalized.get("story_contract_seed")
    if isinstance(seed, dict):
        for key, value in seed.items():
            if key in contract and value not in (None, "", [], {}):
                contract[key] = copy.deepcopy(value)
    return contract


# Back-compat alias used by story_plan / story_normalize / tests.
_draft_story_contract = draft_story_contract


def suggest_story_contract(normalized: dict[str, Any]) -> dict[str, Any]:
    """Suggest story contract fields based on genre and source text.

    Returns a dict with suggested values and a confidence level.
    The caller decides whether to apply these suggestions.
    """
    genre = _text(normalized.get("genre") or "adult")
    template = GENRE_CONTRACT_TEMPLATES.get(genre, DEFAULT_CONTRACT)

    logline = _text(normalized.get("logline") or normalized.get("raw_excerpt") or "")
    characters = normalized.get("character_candidates") or []
    character_names = [c.get("name") or c.get("id") for c in characters if isinstance(c, dict)]

    # Personalize template with character names where possible
    personalized = dict(template)
    if len(character_names) >= 1:
        personalized["protagonist_goal"] = personalized.get("protagonist_goal", "").replace(
            "主角", character_names[0]
        )
    if len(character_names) >= 2:
        personalized["opposition"] = personalized.get("opposition", "").replace(
            "社会规范",
            character_names[1] if character_names[1] != character_names[0] else "外部力量",
        )

    emotional_arc = _extract_emotional_arc(normalized)

    # Derive climax from genre template
    climax = personalized.get("climax_choice", "")
    if genre == "adult":
        climax = "选择彻底交出自己"
    elif genre == "mystery":
        climax = "选择公开真相或保护自己"
    elif genre == "drama":
        climax = "选择坦白或继续沉默"

    contract = {
        "genre": genre,
        "premise": logline,
        "logline": logline,
        "theme": template.get("theme", ""),
        "protagonist_ids": [
            str(c.get("id")) for c in characters if isinstance(c, dict) and c.get("id")
        ][:2],
        "protagonist_goal": personalized.get("protagonist_goal", ""),
        "protagonist_want": personalized.get("protagonist_want", ""),
        "protagonist_need": personalized.get("protagonist_need", ""),
        "protagonist_arc": personalized.get("protagonist_arc", ""),
        "opposition": personalized.get("opposition", ""),
        "stakes": personalized.get("stakes", ""),
        "climax_choice": climax,
        "ending_hook": template.get("ending_hook", ""),
        "emotional_arc": emotional_arc,
        "act_structure": {
            "setup": template.get("protagonist_goal", ""),
            "confrontation": template.get("opposition", ""),
            "resolution": climax,
            "setup_ratio": 0.20,
            "confrontation_ratio": 0.50,
            "resolution_ratio": 0.30,
        },
        "pace_chart": [],
        "constraints": [],
        "status": "draft_suggested",
        "authoring_questions": [
            f"{character_names[0] if character_names else '主角'}想要什么？",
            "谁或什么阻止他？",
            "失败的代价是什么？",
            "本集的关键选择是什么？",
            "结尾留下什么未解决问题？",
        ],
        "confidence": "suggested",
    }

    return contract
