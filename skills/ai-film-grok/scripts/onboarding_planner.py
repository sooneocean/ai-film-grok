"""Agent-style onboarding planner.

Turns a minimal brief (story text + optional lead image) into a reviewable
production plan. Uses the private local LLM when configured (``AIFILM_LOCAL_LLM_*``
env), otherwise falls back to a deterministic heuristic so onboarding never blocks.

The output is a *proposal*: the console must show it as AI-suggested and let the
human confirm/edit before any production state is written.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# zh-CN neural voices (mirrors the web console's ZH_VOICES list).
ZH_VOICES = [
    "zh-CN-XiaoyiNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunyangNeural",
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-liaoning-XiaobeiNeural",
]

ADULT_KEYWORDS = (
    "成人", "情欲", "肉", "做爱", "做愛", "性", "裸", "床戏",
    "暧昧", "调情", "缠绵", "私密", "湿",
)
HEAT_HINTS = {
    "成人": "max", "情欲": "max", "肉": "max", "做爱": "max", "性": "max",
    "热辣": "max", "甜宠": "mild", "纯爱": "mild", "治愈": "mild", "清水": "mild",
}
GENRE_HINTS = {
    "成人": "adult", "爱情": "romance", "悬疑": "thriller", "甜宠": "romance",
    "职场": "drama", "校园": "drama", "治愈": "slife", "科幻": "scifi",
}
MOOD_TO_BGM = {
    "甜": "轻盈甜蜜的流行钢琴", "宠": "轻盈甜蜜的流行钢琴", "虐": "低沉弦乐叙事",
    "悬疑": "紧张脉冲电子", "紧张": "紧张脉冲电子", "治愈": "舒缓原声吉他",
    "忧伤": "忧郁钢琴", "燃": "节奏感强的电子", "性感": "慵懒 R&B", "暧昧": "慵懒 R&B",
}

# Speech verbs that a character name tends to precede in narration.
_SPEECH_VERBS = (
    "说", "道", "问", "笑", "喊", "喃喃", "低声", "轻笑", "叹", "回", "应",
    "答", "嘟囔", "呢喃", "叫", "唤",
)
# Role nouns that often label an unnamed protagonist/supporting cast.
_ROLE_NOUNS = (
    "男人", "女人", "少年", "少女", "青年", "女孩", "男孩", "老板", "先生",
    "小姐", "老师", "医生", "护士", "警察", "律师", "店长", "室友", "邻居",
    "母亲", "父亲", "哥哥", "姐姐", "弟弟", "妹妹", "妻子", "丈夫",
)
# Stop-words that must never be treated as a character name.
_NAME_STOP = ("这个", "那个", "什么", "怎么", "为什么", "这样", "那样", "夜色", "此时", "此刻")

# Theme / tone suggestions keyed by genre (overridden by hint keywords).
_GENRE_THEME = {
    "adult": "欲望与亲密关系的试探",
    "romance": "在日常缝隙里慢慢靠近",
    "thriller": "真相背后的暗流",
    "drama": "普通人的命运褶皱",
    "slife": "温柔自愈的慢时光",
    "scifi": "近未来的人性镜像",
}
_GENRE_TONE = {
    "adult": "暧昧拉扯，近景为主",
    "romance": "甜宠轻快",
    "thriller": "压抑紧绷",
    "drama": "克制写实",
    "slife": "治愈温柔",
    "scifi": "冷峻疏离",
}
_HINT_THEME = {
    "甜宠": "甜到掉牙的双向奔赴", "治愈": "被生活温柔接住", "纯爱": "干干净净的喜欢",
    "悬疑": "环环相扣的谜局", "虐恋": "爱而不得的拉扯", "性感": "危险的吸引力",
}
_HINT_TONE = {
    "甜宠": "轻快明甜", "治愈": "温润舒缓", "纯爱": "清新干净",
    "悬疑": "暗流涌动", "虐恋": "低郁缠绵", "性感": "慵懒撩人",
}
# Shot-hint camera heuristics.
_INTIMACY_KW = ("吻", "抱", "贴", "肌肤", "缠绵", "床", "湿", "靠近", "手指", "耳畔", "唇", "拥抱")
_ACTION_KW = ("跑", "追", "逃", "打", "冲", "搏斗", "扑", "拉", "撞")
_CALM_KW = ("坐", "站", "看", "望", "窗", "雨", "茶", "笑", "风", "灯", "书", "发", "酒")


def decompose(root: Path | str, brief: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return ``(plan, source)`` where source is ``"llm"`` or ``"heuristic"``."""
    base_url = os.environ.get("AIFILM_LOCAL_LLM_BASE_URL", "").strip()
    token = os.environ.get("AIFILM_LOCAL_LLM_TOKEN") or None
    if base_url:
        try:
            from local_llm import decompose as llm_decompose
            from local_llm import probe

            if probe(base_url, token=token).get("ok"):
                lead = (brief.get("image_paths") or [None])[0]
                lead_path = None
                if lead:
                    cand = Path(root).expanduser().resolve() / lead
                    if cand.is_file():
                        lead_path = cand
                result = llm_decompose(
                    base_url,
                    prompt=brief["story_text"],
                    image_path=str(lead_path) if lead_path else None,
                    token=token,
                )
                plan = _normalize_plan(result["candidate"], brief)
                return plan, "llm"
        except Exception:  # noqa: BLE001 -- local LLM must never block onboarding
            pass
    return deterministic_decompose(brief), "heuristic"


def _slug(name: str, idx: int) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]", "", name)
    return clean or f"char{idx + 1}"


def _split_scenes(story: str, limit: int = 8) -> list[dict[str, Any]]:
    chunks = [c.strip() for c in re.split(r"\n\s*\n", story) if c.strip()]
    if not chunks:
        chunks = [story.strip()]
    scenes: list[dict[str, Any]] = []
    for c in chunks[:limit]:
        first_line = c.splitlines()[0].strip()
        scenes.append(
            {
                "title": first_line[:60] or f"段落 {len(scenes) + 1}",
                "summary": c[:300],
                "mood": "",
                "location": "",
            }
        )
    return scenes


def _detect_names(story: str, limit: int = 6) -> list[str]:
    found: list[str] = []
    seen = set()

    def _add(name: str) -> None:
        if name and name not in seen and name not in _NAME_STOP and len(name) <= 4:
            seen.add(name)
            found.append(name)

    # 1) Dialogue prefix: "name：" / "name：" (full/half-width colon) — common in scripts.
    #    Strip any trailing speech verb ("name说：") so we capture the name, not the verb.
    _verb_strip = r"(?:" + "|".join(_SPEECH_VERBS) + r")$"
    for m in re.finditer(r"([一-龥]{1,4})(?:" + "|".join(_SPEECH_VERBS) + r")?[：:]", story):
        name = re.sub(_verb_strip, "", m.group(1))
        _add(name)
    # 2) Speech-verb pattern: a 1-4 char name immediately before 说/道/问/笑/喊/...
    if len(found) < limit:
        for m in re.finditer(r"([一-龥]{1,4})(?:" + "|".join(_SPEECH_VERBS) + ")", story):
            _add(m.group(1))
    # 3) Quoted names: 「名」/“名”/ '名'
    if len(found) < limit:
        for m in re.finditer(r"[「“\"'（(]([一-龥]{1,4})[」”'\"）)]", story):
            _add(m.group(1))
    return found[:limit]


def _infer_genre_heat(story: str, hints: list[str]) -> tuple[str, str]:
    text = story + " " + " ".join(hints)
    for h, heat in HEAT_HINTS.items():
        if h in text:
            genre = GENRE_HINTS.get(h, "adult")
            return genre, heat
    if any(k in story for k in ADULT_KEYWORDS):
        return "adult", "max"
    return "drama", "mild"


def _infer_bgm_mood(story: str, hints: list[str]) -> str:
    text = story + " ".join(hints)
    for kw, mood in MOOD_TO_BGM.items():
        if kw in text:
            return mood
    return "舒缓叙事原声"


def _infer_title(story: str) -> str:
    for line in story.splitlines():
        line = line.strip()
        if line:
            return line[:40]
    return "未命名故事"


def _infer_theme_tone(story: str, genre: str, heat: str, hints: list[str]) -> tuple[str, str]:
    hint = ""
    for h in hints:
        if h in _HINT_THEME:
            hint = h
            break
    theme = _HINT_THEME.get(hint) or _GENRE_THEME.get(genre) or "人物关系的情感切片"
    tone = _HINT_TONE.get(hint) or _GENRE_TONE.get(genre) or "克制写实"
    return theme, tone


def _synthesize_cast(story: str, lead_image: str | None) -> list[dict[str, Any]]:
    """Build a sensible cast when no explicit character name is detected."""
    has_she = bool(re.search(r"她", story))
    has_he = bool(re.search(r"他", story))
    if has_she and has_he:
        seeds = [("女主", "主角", True), ("男主", "配角", False)]
    elif has_she:
        seeds = [("女主", "主角", True)]
    elif has_he:
        seeds = [("男主", "主角", True)]
    else:
        seeds = [("主角", "主角", True)]
    out: list[dict[str, Any]] = []
    for i, (name, role, is_lead) in enumerate(seeds):
        out.append(
            {
                "id": _slug(name, i),
                "name": name,
                "role": role,
                "description": "",
                "is_lead": is_lead,
                "reference_image": lead_image if is_lead else "",
            }
        )
    return out


def _pick_camera(text: str, idx: int) -> str:
    if idx == 0:
        return "全景 · 建立场景与空间关系"
    if any(k in text for k in _INTIMACY_KW):
        return "特写 · 面部与手部微表情"
    if any(k in text for k in _ACTION_KW):
        return "中景手持 · 跟拍动作"
    if any(k in text for k in _CALM_KW):
        return "近景 · 静态双人构图"
    return "中景 · 平视叙事"


def _shot_action(title: str, text: str) -> str:
    core = title or text[:24] or "本场戏"
    action = f"呈现「{core}」的情绪与节奏"
    if len(action) > 120:
        action = action[:117] + "…"
    return action


def _build_shot_hints(
    scenes: list[dict[str, Any]], genre: str, heat: str
) -> list[dict[str, Any]]:
    """Derive reviewable shot hints from the decomposed scenes (heuristic)."""
    hints: list[dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        title = str(sc.get("title") or "")
        summary = str(sc.get("summary") or "")
        text = title + " " + summary
        hints.append({"action": _shot_action(title, text), "camera": _pick_camera(text, i)})
    return hints


def deterministic_decompose(brief: dict[str, Any]) -> dict[str, Any]:
    """Heuristic fallback: no LLM required. Always returns a usable plan."""
    story = str(brief.get("story_text") or "")
    hints = brief.get("hints") or []
    image_paths = brief.get("image_paths") or []

    scenes = _split_scenes(story)
    names = _detect_names(story)
    lead_image = image_paths[0] if image_paths else None

    characters: list[dict[str, Any]] = []
    if names:
        for i, name in enumerate(names):
            characters.append(
                {
                    "id": _slug(name, i),
                    "name": name,
                    "role": "主角" if i == 0 else "配角",
                    "description": "",
                    "is_lead": i == 0,
                    "reference_image": lead_image if i == 0 else "",
                }
            )
    else:
        characters = _synthesize_cast(story, lead_image)

    genre, heat = _infer_genre_heat(story, hints)
    voice_suggestions = [
        {"character_id": c["id"], "voice": ZH_VOICES[i % len(ZH_VOICES)]}
        for i, c in enumerate(characters)
    ]
    bgm_mood = _infer_bgm_mood(story, hints)
    theme, tone = _infer_theme_tone(story, genre, heat, hints)
    shot_hints = _build_shot_hints(scenes, genre, heat)

    return {
        "title": _infer_title(story),
        "genre": genre,
        "heat_scale": heat,
        "theme": theme,
        "tone": tone,
        "characters": characters,
        "scenes": scenes,
        "shot_hints": shot_hints,
        "voice_suggestions": voice_suggestions,
        "bgm_mood": bgm_mood,
        "source_note": "heuristic (no local LLM configured)",
    }


def _normalize_plan(plan: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Make an LLM plan safe + complete: ids, lead image, voice coverage."""
    if not isinstance(plan, dict):
        plan = {}
    characters = plan.get("characters") or []
    if not isinstance(characters, list):
        characters = []
    lead_image = (brief.get("image_paths") or [None])[0]
    norm_chars = []
    for i, c in enumerate(characters):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or _slug(str(c.get("name") or ""), i)).strip()
        if not cid:
            cid = f"char{i + 1}"
        ref = str(c.get("reference_image") or (lead_image if c.get("is_lead") else ""))
        norm_chars.append(
            {
                "id": cid,
                "name": str(c.get("name") or cid),
                "role": str(c.get("role") or ("主角" if i == 0 else "配角")),
                "description": str(c.get("description") or ""),
                "is_lead": bool(c.get("is_lead", i == 0)),
                "reference_image": ref,
            }
        )
    if not norm_chars and lead_image:
        norm_chars.append(
            {
                "id": "lead",
                "name": "主角",
                "role": "主角",
                "description": "",
                "is_lead": True,
                "reference_image": lead_image,
            }
        )

    # ensure every character has a voice suggestion
    existing = {v.get("character_id") for v in (plan.get("voice_suggestions") or []) if isinstance(v, dict)}
    voice_suggestions = list(plan.get("voice_suggestions") or [])
    for i, c in enumerate(norm_chars):
        if c["id"] not in existing:
            voice_suggestions.append({"character_id": c["id"], "voice": ZH_VOICES[i % len(ZH_VOICES)]})

    return {
        "title": str(plan.get("title") or _infer_title(brief.get("story_text", ""))),
        "genre": str(plan.get("genre") or "adult"),
        "heat_scale": str(plan.get("heat_scale") or "max"),
        "theme": str(plan.get("theme") or ""),
        "tone": str(plan.get("tone") or ""),
        "characters": norm_chars,
        "scenes": plan.get("scenes") or [],
        "shot_hints": plan.get("shot_hints") or [],
        "voice_suggestions": voice_suggestions,
        "bgm_mood": str(plan.get("bgm_mood") or "舒缓叙事原声"),
    }
