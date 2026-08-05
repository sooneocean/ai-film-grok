"""Beat extraction: sentence splitting, narrative-weight scoring, beat mapping.

Extracted from story_plan.py to separate the beat-allocation logic from
shot planning and graph construction.  This module is self-contained
(no circular imports with story_plan.py).
"""

from __future__ import annotations

import re
from typing import Any

from beat_spine import load_spine, spine_exists

# ---------------------------------------------------------------------------
# Genre detection constants (parallel to _HEAT_MAX_MARKERS in story_plan.py)
# ---------------------------------------------------------------------------

GENRES = ("adult", "drama", "mystery", "arthouse", "documentary")

_GENRE_MARKERS: dict[str, tuple[str, ...]] = {
    "drama": (
        "剧情",
        "家庭",
        "社会",
        "现实",
        "伦理",
        "成长",
        "亲情",
        "关系",
        "生活",
        "都市情感",
    ),
    "mystery": (
        "悬疑",
        "惊悚",
        "推理",
        "谜",
        "案件",
        "调查",
        "真相",
        "凶杀",
        "侦探",
        "犯罪",
    ),
    "arthouse": (
        "文艺",
        "实验",
        "意象",
        "诗意",
        "留白",
        "氛围",
        "艺术",
        "散文诗",
        "意识流",
    ),
    "documentary": (
        "纪录",
        "纪实",
        "真实",
        "访谈",
        "历史",
        "科普",
        "传记",
        "档案",
        "纪实报道",
    ),
}

GENRE_NAMES = frozenset(GENRES)

# ---------------------------------------------------------------------------
# Authoring prompts
# ---------------------------------------------------------------------------

AUTHORING_PLACEHOLDER = "needs_authoring"

_BEAT_AUTHORING_PROMPTS: dict[str, tuple[str, ...]] = {
    "hook": (
        "主角此刻想得到什么？",
        "第一秒要让观众看见哪一个异常或危险？",
    ),
    "setup": (
        "谁或什么阻止主角？",
        "主角采取什么策略来推进目标？",
    ),
    "escalate": (
        "哪一个新信息或动作改变了局面？",
        "观众在这个 Beat 结束时比开始多知道什么？",
    ),
    "peak": (
        "主角必须做出什么不可撤回的选择？",
        "这个选择让谁获得或失去什么？",
    ),
    "button": (
        "选择造成了什么可见后果？",
        "下一集或下一段必须留下什么问题？",
    ),
}

_GENRE_BEAT_PROMPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "drama": {
        "hook": ("主角此刻的处境是什么？", "观众第一秒看到的张力是什么？"),
        "setup": ("谁与主角有关系？", "空间如何映射关系？"),
        "rising": ("什么行动升级了冲突？", "主角的代价是什么？"),
        "turn": ("什么让主角改变了立场？", "观众在这一拍多懂了什么？"),
        "climax": ("不可撤回的决定是什么？", "谁因此获得或失去？"),
        "resolution": ("新常态长什么样？", "留下了什么未决？"),
    },
    "mystery": {
        "hook": ("谜面是什么？", "观众第一秒看到什么异常？"),
        "investigate": ("谁在调查？", "调查逼近了什么？"),
        "clue": ("哪个物证最关键？", "观众看到了什么角色没看到的东西？"),
        "red_herring": ("什么误导了调查方向？", "假线索的后果是什么？"),
        "reveal": ("真相如何揭露？", "揭露改变了谁的命运？"),
        "aftermath": ("余波中谁受影响？", "什么新疑问被打开？"),
    },
    "arthouse": {
        "mood_open": ("氛围基调是什么？", "观众感受到什么而不是看到什么？"),
        "observe": ("凝视什么？", "细节如何暗示内心？"),
        "gesture": ("什么微妙变化发生了？", "关系微变如何外化？"),
        "silence": ("沉默里涌动什么？", "留白如何说话？"),
        "shift": ("情绪如何转向？", "不是情节转折而是什么转折？"),
        "echo": ("余响指向什么？", "什么未决？"),
    },
    "documentary": {
        "premise": ("主题/问题是什么？", "为什么观众要关心？"),
        "context": ("背景如何建立？", "语境提供什么坐标？"),
        "evidence": ("什么事实/数据支撑主题？", "物证如何呈现？"),
        "perspective": ("谁的立场被表达？", "观点如何补充或冲突？"),
        "conclusion": ("结论指向什么？", "推论如何成立？"),
        "coda": ("余思留下什么？", "什么开放问题？"),
    },
}

# ---------------------------------------------------------------------------
# Sentence splitting & narrative-weight scoring
# ---------------------------------------------------------------------------

_SENTENCE_BEAT_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "hook": (
        "异常",
        "危险",
        "欲望",
        "冲突",
        "意外",
        "震惊",
        "不可",
        "必须",
        "突然",
        "绝不",
        "不可能",
        "秘密",
        "危险",
    ),
    "approach": (
        "靠近",
        "接近",
        "尝试",
        "决定",
        "选择",
        "策略",
        "计划",
        "打算",
        "关系",
        "空间",
        "进入",
        "面对",
    ),
    "sensory": (
        "感觉",
        "感受",
        "触摸",
        "气味",
        "声音",
        "呼吸",
        "心跳",
        "颤抖",
        "温暖",
        "寒冷",
        "疼痛",
        "柔软",
        "眼神",
    ),
    "reaction": (
        "反应",
        "回应",
        "震惊",
        "愤怒",
        "悲伤",
        "喜悦",
        "犹豫",
        "退缩",
        "沉默",
        "转身",
        "离开",
        "停下",
    ),
    "action": (
        "行动",
        "决定",
        "选择",
        "冲击",
        "突破",
        "对抗",
        "抵抗",
        "反击",
        "进攻",
        "防守",
        "争夺",
        "抢夺",
        "推开",
        "抓住",
    ),
    "afterglow": (
        "余韵",
        "回味",
        "留下",
        "结束",
        "之后",
        "终于",
        "结果",
        "后果",
        "未完",
        "待续",
        "钩子",
    ),
}


def _sentences(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", body)
    return [p.strip() for p in parts if p.strip()]


def _sentence_relevance(sentence: str, beat_key: str) -> float:
    """Score how relevant a sentence is to a given beat key (0.0–1.0)."""
    text = sentence.lower()
    keywords = _SENTENCE_BEAT_KEYWORDS.get(beat_key, ())
    if not keywords:
        return 0.5
    hits = sum(1 for kw in keywords if kw in text)
    return min(1.0, hits / max(1, len(keywords)) * 2)


def _assign_sentences_to_beat(
    sents: list[str],
    spine: list[dict[str, Any]],
    beat_index: int,
    spine_len: int,
    scene_budget_sec: float,
) -> list[str]:
    """Assign sentences to a beat using narrative weight scoring.

    Instead of evenly splitting sentences, this scores each sentence
    against the beat's dramatic_function and assigns the most relevant
    ones, weighted by the beat's weight in the spine.
    """
    if spine_len == 1:
        return list(sents)

    sp = spine[beat_index]
    beat_key = sp.get("key", "approach")
    beat_weight = float(sp.get("weight", 0.2))

    scored: list[tuple[float, int, str]] = [
        (_sentence_relevance(s, beat_key), i, s) for i, s in enumerate(sents)
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    total_weight = sum(float(b.get("weight", 0.2)) for b in spine)
    target_count = max(1, round(len(sents) * beat_weight / total_weight))

    selected = sorted(scored[:target_count], key=lambda x: x[1])
    return [s for _, _, s in selected]


# ---------------------------------------------------------------------------
# Spine selection (extracted from story_plan.py)
# ---------------------------------------------------------------------------


def select_beat_spine(
    heat: dict[str, Any] | None = None,
    *,
    genre: str | None = None,
    target_duration: float | None = None,
    multi_scene: bool = False,
) -> list[dict[str, Any]]:
    """Pick beat spine. Genre takes priority; adult defaults to adult_max.

    Spines are loaded from JSON files in schemas/beat-spines/ via
    beat_spine.load_spine().  Any genre that has a corresponding spine
    file (e.g. thriller.json, romance.json) is auto-discovered — no
    hardcoded name list needed.
    """
    # Explicit spine overrides (heat-signal or caller-specified)
    h = heat or {}
    scale = str(h.get("heat_scale") or "").strip().lower()

    # Explicit cool-down only escape from adult max spine
    if scale in {"soft", "medium"}:
        return [dict(b) for b in load_spine("default")]
    # Explicit dual / hardcore overrides
    if h.get("spine") == "dual_climax" or h.get("dual_climax"):
        return [dict(b) for b in load_spine("dual_climax")]
    if h.get("spine") == "hardcore_male" or h.get("hardcore"):
        return [dict(b) for b in load_spine("hardcore_male")]
    # Non-adult genre: auto-discover spine file if it exists; fall back to default
    if genre and genre != "adult" and spine_exists(genre):
        return [dict(b) for b in load_spine(genre)]
    # Adult default IRON: always adult_max (max / unset / adult_max spine / evidence_max)
    if (
        not genre
        or genre == "adult"
        or scale == "max"
        or h.get("spine") == "adult_max"
        or h.get("evidence_max")
    ):
        return [dict(b) for b in load_spine("adult_max")]
    _ = multi_scene  # reserved for future scene-local spines
    _ = target_duration
    return [dict(b) for b in load_spine("default")]


def _genre_spine(genre: str) -> list[dict[str, Any]]:
    """Load a genre spine from JSON. Falls back to default."""
    if spine_exists(genre):
        return load_spine(genre)
    return load_spine("default")


# ---------------------------------------------------------------------------
# Adult beat helpers
# ---------------------------------------------------------------------------


def _compact_adult_spine_for_scene(body: str) -> list[dict[str, Any]]:
    """Multi-scene adult: one short local arc per scene (no full dual-climax clone)."""
    b = body or ""
    has_sex = bool(re.search(r"办事|沉腰|交合|野战|狂干|揉胸|卸装|半裸|缠绵|后入", b))
    has_hook = bool(re.search(r"旁白|诗|钩子|开场|字幕", b))
    spine: list[dict[str, Any]] = []
    if has_hook or not has_sex:
        spine.append(
            {
                "key": "hook",
                "dramatic_function": "hook",
                "objective": "local hook from user section",
                "importance": "high",
                "weight": 0.2,
                "shots_n": 1,
                "heat_phase": "setup",
                "wardrobe_state": "full",
            }
        )
    spine.append(
        {
            "key": "setup",
            "dramatic_function": "approach",
            "objective": "advance this section only",
            "importance": "med",
            "weight": 0.25,
            "shots_n": 1,
            "heat_phase": "foreplay" if has_sex else "setup",
            "coitus_beat": "entry" if has_sex else None,
            "wardrobe_state": "partial" if has_sex else "full",
        }
    )
    if has_sex:
        spine.append(
            {
                "key": "act",
                "dramatic_function": "action",
                "objective": "section peak action: 沉腰抽送",
                "importance": "high",
                "weight": 0.28,
                "shots_n": 1,
                "heat_phase": "act",
                "coitus_beat": "rhythm",
                "wardrobe_state": "undressed",
                "duration_boost": 8.0,
            }
        )
        spine.append(
            {
                "key": "climax",
                "dramatic_function": "action",
                "objective": "section climax: 办穿/射出",
                "importance": "climax",
                "weight": 0.22,
                "shots_n": 1,
                "heat_phase": "climax",
                "coitus_beat": "finish",
                "wardrobe_state": "bare",
                "duration_boost": 6.0,
            }
        )
        spine.append(
            {
                "key": "button",
                "dramatic_function": "afterglow",
                "objective": "section exit / hook out",
                "importance": "med",
                "weight": 0.15,
                "shots_n": 1,
                "heat_phase": "afterglow",
                "coitus_beat": "hook",
                "wardrobe_state": "bare",
            }
        )
    else:
        spine.append(
            {
                "key": "button",
                "dramatic_function": "bridge",
                "objective": "leave section with next-beat pressure",
                "importance": "med",
                "weight": 0.3,
                "shots_n": 1,
                "heat_phase": "setup",
                "wardrobe_state": "full",
            }
        )
    for sp in spine:
        if sp.get("coitus_beat") is None:
            sp.pop("coitus_beat", None)
    return spine


def rebalance_adult_beat_durations(
    beats: list[dict[str, Any]],
    *,
    scene_budget_sec: float,
    sex_floor: float = 0.50,
) -> list[dict[str, Any]]:
    """Ensure act+climax share of beat duration ≥ sex_floor (adult max plan-time).

    Extends meat beats first; does not invent new beats.
    """
    if not beats or scene_budget_sec <= 0:
        return beats
    meat_keys = {"act", "climax"}
    total = sum(float(b.get("targetDuration") or 0) for b in beats) or 0.0
    if total <= 0:
        return beats
    meat = sum(
        float(b.get("targetDuration") or 0)
        for b in beats
        if str(b.get("heat_phase") or "").lower() in meat_keys
    )
    ratio = meat / total
    if ratio + 1e-9 >= sex_floor:
        return beats
    need = sex_floor * total - meat
    meat_beats = [b for b in beats if str(b.get("heat_phase") or "").lower() in meat_keys]
    if not meat_beats:
        return beats
    meat_beats_sorted = sorted(
        meat_beats,
        key=lambda b: (
            0 if str(b.get("coitus_beat") or "") in {"rhythm", "finish"} else 1,
            -float(b.get("targetDuration") or 0),
        ),
    )
    each = need / len(meat_beats_sorted)
    for b in meat_beats_sorted:
        b["targetDuration"] = round(float(b.get("targetDuration") or 0) + each, 1)
        b["_duration_rebalanced"] = True
    new_total = sum(float(b.get("targetDuration") or 0) for b in beats)
    if new_total > scene_budget_sec * 1.15:
        setup_beats = [
            b
            for b in beats
            if str(b.get("heat_phase") or "").lower() in {"setup", "afterglow", "bridge"}
        ]
        overflow = new_total - scene_budget_sec
        for b in setup_beats:
            if overflow <= 0:
                break
            cur = float(b.get("targetDuration") or 0)
            cut = min(overflow, max(0.0, cur - 2.5))
            b["targetDuration"] = round(cur - cut, 1)
            overflow -= cut
    return beats


# ---------------------------------------------------------------------------
# Public beat extraction
# ---------------------------------------------------------------------------


def extract_beats(
    scene: dict[str, Any],
    *,
    scene_budget_sec: float,
    is_only_scene: bool,
    heat: dict[str, Any] | None = None,
    target_duration: float | None = None,
    genre: str | None = None,
) -> list[dict[str, Any]]:
    """beat.extract — map scene body onto vertical beat spine (genre-aware).

    P0-1 · 2026-07-23: non-adult genres use GENRE_SPINES via select_beat_spine.
    Adult genre preserves backward-compat heat-signal logic.
    """
    body = str(scene.get("body") or scene.get("synopsis") or "")
    sents = _sentences(body)
    heat = heat or {}
    adult = (genre or "adult") == "adult" and str(
        heat.get("heat_scale") or ""
    ).strip().lower() not in {"soft", "medium"}
    if adult and not is_only_scene:
        spine = _compact_adult_spine_for_scene(body)
    else:
        spine = select_beat_spine(
            heat,
            genre=genre,
            target_duration=target_duration or scene_budget_sec,
            multi_scene=not is_only_scene,
        )
    is_genre_spine = genre and genre != "adult" and genre in GENRE_NAMES
    if not adult:
        if not is_only_scene and len(sents) <= 2:
            if len(spine) >= 5:
                spine = [spine[0], spine[2], spine[3], spine[4]]
        elif len(sents) == 1 and is_only_scene:
            spine = [dict(b) for b in load_spine("default")] if not is_genre_spine else spine

    if not sents:
        sents = [str(scene.get("synopsis") or scene.get("title") or "画面推进")]

    beats: list[dict[str, Any]] = []
    n = len(spine)
    for bi, sp in enumerate(spine):
        chunk_sents = (
            sents if n == 1 else _assign_sentences_to_beat(sents, spine, bi, n, scene_budget_sec)
        )
        action_text = " ".join(chunk_sents)
        dur = max(2.0, round(float(scene_budget_sec) * float(sp["weight"]), 1))
        boost = sp.get("duration_boost")
        if boost is not None:
            dur = max(dur, float(boost) * int(sp.get("shots_n") or 1))
        beat_id = f"{scene['id']}_bt{bi + 1:02d}_{sp['key']}"
        beat_obj: dict[str, Any] = {
            "id": beat_id,
            "order": bi + 1,
            "key": sp["key"],
            "objective": sp["objective"],
            "action": action_text[:120],
            "outcome": "",
            "emotionalShift": {"from": "", "to": ""},
            "importance": sp["importance"],
            "dramatic_function": sp["dramatic_function"],
            "heat_phase": sp.get("heat_phase"),
            "coitus_beat": sp.get("coitus_beat"),
            "targetDuration": dur,
            "shots_n": min(int(sp["shots_n"]), max(1, len(chunk_sents))),
            "source_text": action_text,
            "obstacle": AUTHORING_PLACEHOLDER,
            "tactic": AUTHORING_PLACEHOLDER,
            "turn": AUTHORING_PLACEHOLDER,
            "state_delta": AUTHORING_PLACEHOLDER,
            "audience_question": AUTHORING_PLACEHOLDER,
            "emotional_turn": AUTHORING_PLACEHOLDER,
            "authoring_questions": list(
                (_GENRE_BEAT_PROMPTS.get(genre or "", {}) or _BEAT_AUTHORING_PROMPTS).get(
                    sp["key"], ()
                )
            ),
        }
        if sp.get("heat_phase"):
            beat_obj["heat_phase"] = sp["heat_phase"]
        if sp.get("coitus_beat"):
            beat_obj["coitus_beat"] = sp["coitus_beat"]
        if sp.get("wardrobe_state"):
            beat_obj["wardrobe_state"] = sp["wardrobe_state"]
        beats.append(beat_obj)
    if adult:
        floor = 0.55 if heat.get("hardcore") else 0.50
        beats = rebalance_adult_beat_durations(
            beats, scene_budget_sec=scene_budget_sec, sex_floor=floor
        )
    return beats
