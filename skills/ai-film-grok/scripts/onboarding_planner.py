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
    # Chinese speech-verb pattern: a 1-4 char name immediately before 说/道/问/笑/...
    found: list[str] = []
    seen = set()
    for m in re.finditer(r"([一-龥]{1,4})(?:说|道|问|笑|喊|喃喃|低声|轻笑|叹)", story):
        name = m.group(1)
        if name and name not in seen and name not in ("这个", "那个", "什么", "怎么"):
            seen.add(name)
            found.append(name)
    # Quoted names: 「名」/“名”/ '名'
    if len(found) < limit:
        for m in re.finditer(r"[「“\"'（(]([一-龥]{1,4})[」”'\"）)]", story):
            name = m.group(1)
            if name and name not in seen:
                seen.add(name)
                found.append(name)
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


def deterministic_decompose(brief: dict[str, Any]) -> dict[str, Any]:
    """Heuristic fallback: no LLM required. Always returns a usable plan."""
    story = str(brief.get("story_text") or "")
    hints = brief.get("hints") or []
    image_paths = brief.get("image_paths") or []

    scenes = _split_scenes(story)
    names = _detect_names(story)
    lead_image = image_paths[0] if image_paths else None

    characters: list[dict[str, Any]] = []
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
    if not characters and lead_image:
        characters.append(
            {
                "id": "lead",
                "name": "主角",
                "role": "主角",
                "description": "",
                "is_lead": True,
                "reference_image": lead_image,
            }
        )

    genre, heat = _infer_genre_heat(story, hints)
    voice_suggestions = [
        {"character_id": c["id"], "voice": ZH_VOICES[i % len(ZH_VOICES)]}
        for i, c in enumerate(characters)
    ]
    bgm_mood = _infer_bgm_mood(story, hints)

    return {
        "title": _infer_title(story),
        "genre": genre,
        "heat_scale": heat,
        "theme": "",
        "tone": "",
        "characters": characters,
        "scenes": scenes,
        "shot_hints": [],
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
