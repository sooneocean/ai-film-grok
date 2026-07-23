#!/usr/bin/env python3
"""Phase 3: story.normalize → episode/scene/beat/shot planning.

Deterministic structure planner for vertical (9:16) drama.
Does NOT call external LLMs — Agent may refine nar/dsl after plan run.
Produces drama-graph.json (planned) + optional film-spec seed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from narrative_control import (
    GRAPH_SCHEMA_VERSION,
    draft_director_board,
    ensure_graph_controls,
    graph_content_sha256,
    validate_narrative_graph,
)
from util import read_json, write_json

# film-spec dramatic_function enum
DRAMATIC_FUNCS = (
    "hook",
    "approach",
    "sensory",
    "reaction",
    "action",
    "afterglow",
    "bridge",
)

# Default vertical short-form beat spine (hook → ending hook)
DEFAULT_BEAT_SPINE: list[dict[str, Any]] = [
    {
        "key": "hook",
        "dramatic_function": "hook",
        "importance": "climax",
        "objective": "开场钩子：异常/欲望/冲突入口",
        "weight": 0.12,
        "shots_n": 1,
    },
    {
        "key": "setup",
        "dramatic_function": "approach",
        "importance": "supporting",
        "objective": "建立人物关系与空间",
        "weight": 0.18,
        "shots_n": 1,
    },
    {
        "key": "escalate",
        "dramatic_function": "sensory",
        "importance": "important",
        "objective": "情绪/信息升级",
        "weight": 0.22,
        "shots_n": 2,
    },
    {
        "key": "peak",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "高潮或关键决定",
        "weight": 0.28,
        "shots_n": 2,
    },
    {
        "key": "button",
        "dramatic_function": "afterglow",
        "importance": "supporting",
        "objective": "余韵与下一集钩子",
        "weight": 0.20,
        "shots_n": 1,
    },
]

# Adult max spine: setup short → foreplay undress → act multi → climax → hook
# Duration weights reserve ≥35% for act+climax (product floor 20%; hardcore 40%)
ADULT_MAX_BEAT_SPINE: list[dict[str, Any]] = [
    {
        "key": "hook",
        "dramatic_function": "hook",
        "importance": "important",
        "objective": "落锁/边界关闭：今晚只办你",
        "weight": 0.08,
        "shots_n": 1,
        "heat_phase": "setup",
        "coitus_beat": "entry",
        "wardrobe_state": "full",
    },
    {
        "key": "foreplay",
        "dramatic_function": "sensory",
        "importance": "important",
        "objective": "前戏失序：卸甲/脱衣到半裸",
        "weight": 0.12,
        "shots_n": 1,
        "heat_phase": "foreplay",
        "coitus_beat": "undress",
        "wardrobe_state": "partial",
    },
    {
        "key": "foreplay2",
        "dramatic_function": "approach",
        "importance": "supporting",
        "objective": "贴身权力：拽入跨坐起势",
        "weight": 0.10,
        "shots_n": 1,
        "heat_phase": "foreplay",
        "coitus_beat": "entry",
        "wardrobe_state": "partial",
    },
    {
        "key": "union",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "结合：跨坐落稳骨盆咬合",
        "weight": 0.12,
        "shots_n": 1,
        "heat_phase": "act",
        "coitus_beat": "union",
        "wardrobe_state": "undressed",
        "duration_boost": 8.0,
    },
    {
        "key": "rhythm",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "节奏：沉腰顶磨至少两次起伏",
        "weight": 0.18,
        "shots_n": 2,
        "heat_phase": "act",
        "coitus_beat": "rhythm",
        "wardrobe_state": "undressed",
        "duration_boost": 8.0,
    },
    {
        "key": "lock",
        "dramatic_function": "sensory",
        "importance": "important",
        "objective": "锁紧：腿锁腰/攥布特写",
        "weight": 0.10,
        "shots_n": 1,
        "heat_phase": "act",
        "coitus_beat": "lock",
        "wardrobe_state": "bare",
    },
    {
        "key": "climax",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "办完：失声拱背腿软",
        "weight": 0.14,
        "shots_n": 1,
        "heat_phase": "climax",
        "coitus_beat": "finish",
        "wardrobe_state": "bare",
        "duration_boost": 8.0,
    },
    {
        "key": "button",
        "dramatic_function": "afterglow",
        "importance": "supporting",
        "objective": "余韵钩子：下一场换你顶",
        "weight": 0.06,
        "shots_n": 1,
        "heat_phase": "afterglow",
        "coitus_beat": "hook",
        "wardrobe_state": "bare",
    },
]

HARDCORE_MALE_BEAT_SPINE: list[dict[str, Any]] = [
    {**ADULT_MAX_BEAT_SPINE[0], "weight": 0.06},
    {**ADULT_MAX_BEAT_SPINE[1], "weight": 0.08},
    {**ADULT_MAX_BEAT_SPINE[2], "weight": 0.08},
    {**ADULT_MAX_BEAT_SPINE[3], "weight": 0.12, "shots_n": 1},
    {**ADULT_MAX_BEAT_SPINE[4], "weight": 0.22, "shots_n": 2},  # more rhythm
    {
        "key": "rhythm2",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "第二轮节奏：换姿再沉腰",
        "weight": 0.12,
        "shots_n": 1,
        "heat_phase": "act",
        "coitus_beat": "rhythm",
        "wardrobe_state": "bare",
        "duration_boost": 8.0,
    },
    {**ADULT_MAX_BEAT_SPINE[5], "weight": 0.08},
    {**ADULT_MAX_BEAT_SPINE[6], "weight": 0.14, "shots_n": 1},
    {
        "key": "climax2",
        "dramatic_function": "reaction",
        "importance": "climax",
        "objective": "完成脸/余颤反应",
        "weight": 0.06,
        "shots_n": 1,
        "heat_phase": "climax",
        "coitus_beat": "finish",
        "wardrobe_state": "bare",
    },
    {**ADULT_MAX_BEAT_SPINE[7], "weight": 0.04},
]

# 90–120s dual-round: second union/rhythm/finish after brief breath
DUAL_CLIMAX_BEAT_SPINE: list[dict[str, Any]] = [
    {**ADULT_MAX_BEAT_SPINE[0], "weight": 0.05},
    {**ADULT_MAX_BEAT_SPINE[1], "weight": 0.07},
    {**ADULT_MAX_BEAT_SPINE[2], "weight": 0.06},
    {**ADULT_MAX_BEAT_SPINE[3], "weight": 0.10, "shots_n": 1},
    {**ADULT_MAX_BEAT_SPINE[4], "weight": 0.14, "shots_n": 2},
    {**ADULT_MAX_BEAT_SPINE[5], "weight": 0.06},
    {
        "key": "climax1",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "第一轮办完：失声腿软",
        "weight": 0.08,
        "shots_n": 1,
        "heat_phase": "climax",
        "coitus_beat": "finish",
        "wardrobe_state": "bare",
        "duration_boost": 8.0,
    },
    {
        "key": "breath",
        "dramatic_function": "sensory",
        "importance": "supporting",
        "objective": "喘息换姿：未完加办",
        "weight": 0.05,
        "shots_n": 1,
        "heat_phase": "foreplay",
        "coitus_beat": "entry",
        "wardrobe_state": "bare",
    },
    {
        "key": "union2",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "第二轮结合：换姿再落稳",
        "weight": 0.09,
        "shots_n": 1,
        "heat_phase": "act",
        "coitus_beat": "union",
        "wardrobe_state": "bare",
        "duration_boost": 8.0,
    },
    {
        "key": "rhythm3",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "第二轮节奏：更深沉腰",
        "weight": 0.14,
        "shots_n": 2,
        "heat_phase": "act",
        "coitus_beat": "rhythm",
        "wardrobe_state": "bare",
        "duration_boost": 8.0,
    },
    {
        "key": "climax2",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "第二轮办穿：拱背余颤",
        "weight": 0.10,
        "shots_n": 1,
        "heat_phase": "climax",
        "coitus_beat": "finish",
        "wardrobe_state": "bare",
        "duration_boost": 8.0,
    },
    {**ADULT_MAX_BEAT_SPINE[7], "weight": 0.06},
]

# Brief signals → heat (never pin max without evidence)
_HEAT_MAX_MARKERS: tuple[str, ...] = (
    "成人",
    "办事",
    "性爱",
    "里番",
    "色气",
    "大尺度",
    "尺度拉满",
    "heat max",
    "heat_scale=max",
    "heat_scale:max",
    "18+",
    "r18",
    "hentai",
    "ecchi",
    "porn",
    "nsfw",
    "做爱",
    "性交",
    "高潮",
    "沉腰",
)
_HARDCORE_MARKERS: tuple[str, ...] = (
    "重口",
    "男向",
    "hardcore",
    "尺度太小",
    "不够色",
    "重口男向",
    "硬核",
)
_DUAL_CLIMAX_MARKERS: tuple[str, ...] = (
    "双高潮",
    "两轮",
    "第二轮",
    "再来一轮",
    "dual climax",
    "two rounds",
    "double climax",
    "加办第二场",
)
_SPICY_NAR: dict[str, str] = {
    "setup": "展厅落锁。今晚只加演你一场。",
    "foreplay": "肩带一滑，规矩失效，卸到半裸。",
    "act": "沉腰吃进。再顶，磨到发软。",
    "climax": "失声办穿。背一弓，腿软。",
    "afterglow": "贴耳：下一场——换你顶。",
    "bridge": "门闩还热，故事未完。",
}
_SPICY_NAR_EXTREME: dict[str, str] = {
    "setup": "门落锁。今晚只办事加演你。",
    "foreplay": "扣子崩开。半裸卸甲，湿了失序。",
    "act": "沉腰吃进整根。再顶深，磨到发软。",
    "climax": "失声办穿。高潮绞紧，腿软。",
    "afterglow": "咬耳：下一场——换你顶。",
    "bridge": "还湿着。故事未完。",
}
# Template pollution markers (金瓶梅案 · 2026-07-22): these must NEVER replace user script nars
_TEMPLATE_NAR_MARKERS: tuple[str, ...] = (
    "展厅落锁",
    "今晚只加演你",
    "今晚只办事加演",
    "肩带一滑，规矩失效",
    "肩带一滑。卸甲半裸",
    "贴耳：下一场",
    "咬耳：下一场",
    "门落锁。今晚只办事",
    "跨坐落稳。整根吃进",
    "门闩还热，故事未完",
)
# Meta labels that must not become cast names
_CHAR_META_BLOCKLIST: frozenset[str] = frozenset(
    {
        "标题",
        "基调",
        "尺度",
        "角色",
        "旁白",
        "格式",
        "整体基调",
        "总时长建议",
        "剧集标题",
        "时长",
        "集尾",
        "集尾字幕",
        "开场",
        "转场",
    }
)
_BULLET_CHAR = re.compile(
    r"^[\-\*·]\s*([^\s:：\-\d]{2,12})\s*[:：]",
    re.MULTILINE,
)
_TIME_OR_BRACKET_SECTION = re.compile(
    r"(?:^|\n)\s*(?:"
    r"【[^】]{2,40}】"  # 【00:00-00:10 开场】
    r"|#{1,3}\s+[^\n]{2,60}"  # ### 第1集
    r"|\*\*[^\n]{2,60}\*\*"  # **第1集**
    r"|(?:第[一二三四五六七八九十\d]+集)[^\n]{0,40}"
    r")\s*",
    re.MULTILINE,
)


def is_template_nar(nar: object) -> bool:
    """True when nar is pure adult-max template, not user story language."""
    text = str(nar or "").strip()
    if not text:
        return False
    return any(m in text for m in _TEMPLATE_NAR_MARKERS)


def _user_nar_substantive(text: str) -> bool:
    """User-sourced line long enough / distinct from empty filler."""
    t = (text or "").strip()
    if len(t) < 4:
        return False
    if t in {"……", "...", "画面推进", "needs_authoring"}:
        return False
    return not is_template_nar(t)


def preserve_user_nar(
    user_piece: str,
    *,
    heat_phase: str = "",
    coitus_beat: str = "",
    extreme_seed: bool = False,
    max_chars: int = 48,
) -> str:
    """P0 · user source fidelity: keep user VO; only *augment* spice if missing.

    Never wholesale-replace user script lines with _SPICY_NAR templates
    (金瓶梅案: 展厅落锁 overwrote 二八佳人 / 财可通神).
    """
    from edit_policy import nar_has_sex_verb, nar_has_spice

    piece = (user_piece or "").strip()
    ph = (heat_phase or "").strip().lower()
    cb = (coitus_beat or "").strip().lower()
    bank = _SPICY_NAR_EXTREME if extreme_seed else _SPICY_NAR

    # Fallback templates only when beat has no real user text
    if not _user_nar_substantive(piece):
        if cb == "rhythm":
            seed = (
                "沉腰吃进整根。再顶深，磨到发软。" if extreme_seed else "沉腰吃进。再顶，磨到发软。"
            )
        elif cb == "union":
            seed = "跨坐落稳。整根吃进，锁住。"
        elif cb == "lock":
            seed = "腿锁腰。攥床单，再夹紧。"
        elif cb == "finish":
            seed = "失声办穿。高潮绞紧，腿软。" if extreme_seed else "失声办穿。背一弓，腿软。"
        elif cb == "undress":
            seed = "肩带一滑。卸甲半裸，规矩失效。"
        elif cb == "hook":
            seed = "贴耳：下一场——换你顶。" if not extreme_seed else "咬耳：下一场——换你顶。"
        elif ph in bank:
            seed = bank[ph]
        else:
            seed = piece or "画面推进"
        return _clip_nar(seed, max_chars)

    # Preserve user text; spice-augment only if sex_vo gate would fail
    nar = _clip_nar(piece, max_chars)
    need_sex = ph in {"act", "climax"}
    if need_sex and not nar_has_sex_verb(nar):
        tag = "沉腰" if "沉腰" not in nar else "办穿"
        if len(nar) + len(tag) + 1 <= max_chars:
            nar = f"{nar.rstrip('。.!！')}。{tag}。"
        else:
            nar = _clip_nar(f"{nar}{tag}", max_chars)
    elif not nar_has_spice(nar):
        # light dual-entendre suffix that hits spice markers without erasing story
        tag = "色" if "色" not in nar else "喘"
        if len(nar) + 1 <= max_chars and tag not in nar:
            nar = _clip_nar(nar + tag, max_chars)
    return nar


def detect_heat_signals(text: str) -> dict[str, Any]:
    """Parse brief for heat_scale / hardcore — evidence only, no silent pin."""
    raw = (text or "").strip()
    low = raw.lower()
    hardcore = any(m.lower() in low or m in raw for m in _HARDCORE_MARKERS)
    dual = any(m.lower() in low or m in raw for m in _DUAL_CLIMAX_MARKERS)
    want_max = hardcore or dual or any(m.lower() in low or m in raw for m in _HEAT_MAX_MARKERS)
    heat_scale = "max" if want_max else None
    audience_profile = "hardcore_male" if hardcore else None
    spine = "default"
    if dual:
        spine = "dual_climax"
    elif hardcore:
        spine = "hardcore_male"
    elif want_max:
        spine = "adult_max"
    return {
        "heat_scale": heat_scale,
        "audience_profile": audience_profile,
        "spine": spine,
        "hardcore": hardcore or dual,
        "dual_climax": dual,
        "evidence_max": want_max,
    }


def detect_genre(
    text: str,
    *,
    heat: dict[str, Any] | None = None,
    explicit_genre: str | None = None,
) -> dict[str, Any]:
    """Detect genre from brief text signals (parallel to detect_heat_signals).

    Priority: explicit_genre > adult heat signals > genre markers > default adult.
    Returns dict with 'genre', 'evidence', 'warnings'.
    """
    raw = (text or "").strip()
    low = raw.lower()

    # Explicit genre field wins
    if explicit_genre and explicit_genre in GENRES:
        return {
            "genre": explicit_genre,
            "evidence": "explicit_field",
            "warnings": [],
        }

    # Adult heat signals take priority over other genre markers
    h = heat or {}
    if h.get("evidence_max") or h.get("heat_scale") == "max" or h.get("hardcore"):
        return {
            "genre": "adult",
            "evidence": "heat_signals",
            "warnings": [],
        }

    # Match genre markers in order
    matched: list[str] = []
    for genre_key, markers in _GENRE_MARKERS.items():
        if any(m.lower() in low or m in raw for m in markers):
            matched.append(genre_key)

    if matched:
        genre = matched[0]
        warnings: list[str] = []
        if len(matched) > 1:
            warnings.append(
                f"multiple genre signals detected ({', '.join(matched)}); "
                f"using first: {genre} — set genre explicitly to override"
            )
        return {
            "genre": genre,
            "evidence": "text_markers",
            "warnings": warnings,
        }

    # Default: adult (backward compat)
    return {
        "genre": "adult",
        "evidence": "default",
        "warnings": [],
    }


def select_beat_spine(
    heat: dict[str, Any] | None = None,
    *,
    genre: str | None = None,
    target_duration: float | None = None,
    multi_scene: bool = False,
) -> list[dict[str, Any]]:
    """Pick beat spine. Genre takes priority; adult spine falls back to heat logic.

    P0-1 · 2026-07-23: multi-genre support. Non-adult genres use GENRE_SPINES.
    Adult genre (default) preserves backward-compat heat-signal logic.
    """
    # Non-adult genre: use genre spine directly
    if genre and genre != "adult" and genre in GENRE_SPINES:
        return [dict(b) for b in GENRE_SPINES[genre]]

    h = heat or {}
    # Explicit dual only — never infer solely from duration
    if h.get("spine") == "dual_climax" or h.get("dual_climax"):
        return list(DUAL_CLIMAX_BEAT_SPINE)
    if h.get("spine") == "hardcore_male" or h.get("hardcore"):
        return list(HARDCORE_MALE_BEAT_SPINE)
    if h.get("spine") == "adult_max" or h.get("heat_scale") == "max":
        # multi-scene: still adult_max once per scene, not dual
        return list(ADULT_MAX_BEAT_SPINE)
    _ = multi_scene  # reserved for future scene-local spines
    _ = target_duration
    return list(DEFAULT_BEAT_SPINE)


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

# ---------------------------------------------------------------------------
# P0-1 · 2026-07-23: Multi-genre beat spines (de-type-bias)
#
# dramatic_function 七值枚举不变（向后兼容 write-spec 门禁），
# 但 beat spine 按 genre 切换。成人仍是默认但不再是唯一骨架。
# 详见 references/beat-spines.md
# ---------------------------------------------------------------------------

GENRES = ("adult", "drama", "mystery", "arthouse", "documentary")

# Genre signal markers for detect_genre() — parallel to _HEAT_MAX_MARKERS.
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

# Genre-specific beat spines. All dramatic_function values must be in DRAMATIC_FUNCS.
# Each beat: key / dramatic_function / importance / objective / weight / shots_n
GENRE_SPINES: dict[str, list[dict[str, Any]]] = {
    "drama": [
        {
            "key": "hook",
            "dramatic_function": "hook",
            "importance": "climax",
            "objective": "建立人物处境与核心张力",
            "weight": 0.12,
            "shots_n": 1,
        },
        {
            "key": "setup",
            "dramatic_function": "approach",
            "importance": "supporting",
            "objective": "人物关系与空间建立",
            "weight": 0.18,
            "shots_n": 1,
        },
        {
            "key": "rising",
            "dramatic_function": "action",
            "importance": "important",
            "objective": "冲突升级，主角行动推进",
            "weight": 0.22,
            "shots_n": 2,
        },
        {
            "key": "turn",
            "dramatic_function": "reaction",
            "importance": "important",
            "objective": "转折点：反应/抉择/觉醒",
            "weight": 0.20,
            "shots_n": 1,
        },
        {
            "key": "climax",
            "dramatic_function": "action",
            "importance": "climax",
            "objective": "高潮：决定性对抗或选择",
            "weight": 0.18,
            "shots_n": 1,
        },
        {
            "key": "resolution",
            "dramatic_function": "afterglow",
            "importance": "supporting",
            "objective": "结果沉淀与新常态",
            "weight": 0.10,
            "shots_n": 1,
        },
    ],
    "mystery": [
        {
            "key": "hook",
            "dramatic_function": "hook",
            "importance": "climax",
            "objective": "谜面/异常事件抛出",
            "weight": 0.14,
            "shots_n": 1,
        },
        {
            "key": "investigate",
            "dramatic_function": "approach",
            "importance": "important",
            "objective": "调查深入，信息逼近",
            "weight": 0.20,
            "shots_n": 2,
        },
        {
            "key": "clue",
            "dramatic_function": "sensory",
            "importance": "important",
            "objective": "关键线索/物证特写",
            "weight": 0.16,
            "shots_n": 1,
        },
        {
            "key": "red_herring",
            "dramatic_function": "reaction",
            "importance": "supporting",
            "objective": "误导/假线索反应",
            "weight": 0.14,
            "shots_n": 1,
        },
        {
            "key": "reveal",
            "dramatic_function": "action",
            "importance": "climax",
            "objective": "真相揭露/行动推进",
            "weight": 0.24,
            "shots_n": 2,
        },
        {
            "key": "aftermath",
            "dramatic_function": "afterglow",
            "importance": "supporting",
            "objective": "余波与新疑问",
            "weight": 0.12,
            "shots_n": 1,
        },
    ],
    "arthouse": [
        {
            "key": "mood_open",
            "dramatic_function": "hook",
            "importance": "important",
            "objective": "建立氛围与情绪基调",
            "weight": 0.16,
            "shots_n": 1,
        },
        {
            "key": "observe",
            "dramatic_function": "sensory",
            "importance": "climax",
            "objective": "静观：人物/环境的感官凝视",
            "weight": 0.22,
            "shots_n": 2,
        },
        {
            "key": "gesture",
            "dramatic_function": "approach",
            "importance": "important",
            "objective": "微妙接近/关系微变",
            "weight": 0.18,
            "shots_n": 1,
        },
        {
            "key": "silence",
            "dramatic_function": "reaction",
            "importance": "important",
            "objective": "留白/沉默中的情绪涌动",
            "weight": 0.18,
            "shots_n": 1,
        },
        {
            "key": "shift",
            "dramatic_function": "action",
            "importance": "supporting",
            "objective": "情绪转折（非情节转折）",
            "weight": 0.14,
            "shots_n": 1,
        },
        {
            "key": "echo",
            "dramatic_function": "afterglow",
            "importance": "supporting",
            "objective": "回响/未决的余韵",
            "weight": 0.12,
            "shots_n": 1,
        },
    ],
    "documentary": [
        {
            "key": "premise",
            "dramatic_function": "hook",
            "importance": "important",
            "objective": "主题/问题引入",
            "weight": 0.14,
            "shots_n": 1,
        },
        {
            "key": "context",
            "dramatic_function": "approach",
            "importance": "supporting",
            "objective": "背景/语境建立",
            "weight": 0.18,
            "shots_n": 1,
        },
        {
            "key": "evidence",
            "dramatic_function": "sensory",
            "importance": "climax",
            "objective": "事实/数据/物证呈现",
            "weight": 0.22,
            "shots_n": 2,
        },
        {
            "key": "perspective",
            "dramatic_function": "reaction",
            "importance": "important",
            "objective": "观点/访谈/立场",
            "weight": 0.20,
            "shots_n": 1,
        },
        {
            "key": "conclusion",
            "dramatic_function": "action",
            "importance": "important",
            "objective": "结论/推论推进",
            "weight": 0.16,
            "shots_n": 1,
        },
        {
            "key": "coda",
            "dramatic_function": "afterglow",
            "importance": "supporting",
            "objective": "余思/开放问题",
            "weight": 0.10,
            "shots_n": 1,
        },
    ],
}

# Authoring prompts for non-adult genre beat keys (parallel to _BEAT_AUTHORING_PROMPTS)
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

_SCENE_HDR = re.compile(
    r"^(?:#{1,3}\s*|场景\s*[:：]?\s*|Scene\s*\d*\s*[:：]?\s*|第[一二三四五六七八九十\d]+场\s*[:：]?\s*)(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_CHAR_LINE = re.compile(
    r"(?:角色|人物|女主|男主|主角|配角)\s*[:：]\s*(.+)$",
    re.MULTILINE,
)
_DIALOGUE = re.compile(r"^[\s]*([^\s:：]{1,12})\s*[:：]\s*(.+)$", re.MULTILINE)
_NAME_CAND = re.compile(r"[\u4e00-\u9fff]{2,4}")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _slug(text: str, fallback: str = "x") -> str:
    s = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", (text or "").strip())[:40].strip("_")
    # film-spec shot ids must be ascii-ish for validate_identifier — keep latin
    s2 = re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:32].strip("_")
    return s2 or fallback


def _clip_nar(text: str, max_chars: int = 55) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return "……"
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _est_vo_sec(nar: str) -> float:
    """Match film_spec.estimate_nar_vo_sec (zh ≈ 4 chars/s)."""
    t = (nar or "").strip()
    if not t:
        return 0.0
    return max(1.0, round(len(t) / 4.0, 2))


def _duration_for_nar(nar: str, floor: float = 3.0) -> float:
    """Ensure write-spec vo_pacing: est_vo ≤ duration + 0.5."""
    need = _est_vo_sec(nar) + 0.5 + 0.05
    return max(float(floor), round(need, 1))


def _split_paragraphs(raw: str) -> list[str]:
    parts = re.split(r"\n\s*\n+", (raw or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _extract_title(raw: str, title_hint: str | None) -> str:
    if title_hint and title_hint.strip():
        return title_hint.strip()[:80]
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        return "untitled-drama"
    first = lines[0]
    if first.startswith("#"):
        return first.lstrip("#").strip()[:80] or "untitled-drama"
    if len(first) <= 24:
        return first
    # one-liner idea → short title from first 12 chars
    return first[:12].rstrip("，。,. ") + ("…" if len(first) > 12 else "")


def _character_candidates(raw: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name: str, role: str = "supporting") -> None:
        n = name.strip().strip("、，, ")
        # strip trailing descriptors after fullwidth colon already split
        n = re.split(r"[（(]", n, maxsplit=1)[0].strip()
        if not n or n in seen or len(n) > 12:
            return
        if n in _CHAR_META_BLOCKLIST:
            return
        # reject pure punctuation / section meta
        if re.fullmatch(r"[\d\W_]+", n):
            return
        seen.add(n)
        cid = _slug(n, f"char{len(found) + 1}")
        # force ascii id
        if not re.match(r"^[A-Za-z]", cid):
            cid = f"c{len(found) + 1}_{cid}" if cid else f"char{len(found) + 1}"
            cid = re.sub(r"[^A-Za-z0-9_-]", "", cid) or f"char{len(found) + 1}"
        found.append({"id": cid, "name": n, "role": role, "source": "extract"})

    for m in _CHAR_LINE.finditer(raw or ""):
        for part in re.split(r"[、,，/|]", m.group(1)):
            add(part, "lead")

    # Bullet cast lines: - 西门庆：俊朗霸道…
    for m in _BULLET_CHAR.finditer(raw or ""):
        add(m.group(1), "lead")

    for m in _DIALOGUE.finditer(raw or ""):
        speaker = m.group(1).strip()
        if speaker not in {"旁白", "OS", "VO", "内心", "集尾字幕", "集尾"}:
            if speaker not in _CHAR_META_BLOCKLIST:
                add(speaker, "speaking")

    # keyword roles (only when extract empty — avoid polluting named-cast scripts)
    if not found:
        if re.search(r"女主|她|姑娘|司机", raw or ""):
            found.insert(0, {"id": "hero", "name": "女主", "role": "lead", "source": "default"})
        if re.search(r"男主|他|乘客|对方", raw or ""):
            if "partner" not in {c["id"] for c in found}:
                found.append({"id": "partner", "name": "男主", "role": "lead", "source": "default"})

    if not found:
        found = [
            {"id": "hero", "name": "主角", "role": "lead", "source": "default"},
        ]
    return found[:8]


def _location_candidates(raw: str) -> list[dict[str, Any]]:
    locs: list[dict[str, Any]] = []
    patterns = [
        (r"雨夜|出租车|后座|车内", "cab_rain", "雨夜出租车内"),
        (r"卧室|床上|房间", "bedroom", "室内卧室"),
        (r"酒吧|夜店", "bar", "酒吧"),
        (r"街道|巷|路边", "street", "街道"),
        (r"办公室|工位", "office", "办公室"),
        (r"学校|教室", "school", "学校"),
        (r"咖啡", "cafe", "咖啡馆"),
    ]
    for pat, lid, desc in patterns:
        if re.search(pat, raw or ""):
            locs.append({"id": lid, "description": desc, "source": "extract"})
    if not locs:
        locs.append({"id": "loc_main", "description": "主场景（待定）", "source": "default"})
    return locs[:6]


def _dialogue_blocks(raw: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for i, m in enumerate(_DIALOGUE.finditer(raw or ""), start=1):
        blocks.append(
            {
                "id": f"dlg_{i:02d}",
                "speaker": m.group(1).strip(),
                "text": m.group(2).strip()[:120],
            }
        )
    return blocks[:40]


def _scene_chunks(raw: str) -> list[dict[str, str]]:
    """Split source into scene-sized text chunks.

    Prefers explicit headers / 【time】 sections so multi-beat user scripts
    stay independent scenes (not one mush + template spine).
    """
    text = (raw or "").strip()
    if not text:
        return [{"title": "main", "body": ""}]

    # Explicit scene headers
    matches = list(_SCENE_HDR.finditer(text))
    if matches:
        chunks: list[dict[str, str]] = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            title = m.group(1).strip()[:40] if m.lastindex else f"Scene {i + 1}"
            chunks.append({"title": title or f"Scene {i + 1}", "body": body or title})
        if chunks:
            return chunks

    # 【00:00-00:10 …】 / ### 第N集 / **第N集** time-bracket sections
    sec_matches = list(_TIME_OR_BRACKET_SECTION.finditer(text))
    if len(sec_matches) >= 2:
        chunks = []
        for i, m in enumerate(sec_matches):
            title = m.group(0).strip().strip("#*").strip()[:40] or f"S{i + 1}"
            start = m.end()
            end = sec_matches[i + 1].start() if i + 1 < len(sec_matches) else len(text)
            body = text[start:end].strip()
            # skip pure metadata sections (角色表 / 格式) with no VO/action
            if not body and "角色" in title:
                continue
            chunks.append({"title": title, "body": body or title})
        if len(chunks) >= 2:
            return chunks[:8]

    paras = _split_paragraphs(text)
    if len(paras) == 1:
        # one-liner or single block → one scene
        return [{"title": "Main", "body": paras[0]}]
    if len(paras) <= 4:
        return [{"title": f"S{i + 1}", "body": p} for i, p in enumerate(paras)]
    # merge into ~3 scenes
    n = 3
    size = max(1, (len(paras) + n - 1) // n)
    chunks = []
    for i in range(0, len(paras), size):
        group = paras[i : i + size]
        chunks.append({"title": f"S{len(chunks) + 1}", "body": "\n\n".join(group)})
    return chunks[:6]


def normalize_story(
    raw: str,
    *,
    title_hint: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    """story.normalize — structured story package (no LLM)."""
    raw = (raw or "").strip()
    title = _extract_title(raw, title_hint)
    chars = _character_candidates(raw)
    locs = _location_candidates(raw)
    dialogues = _dialogue_blocks(raw)
    chunks = _scene_chunks(raw)
    logline = _clip_nar(raw.replace("\n", " "), 80)
    if len(raw) > 80:
        # prefer first sentence
        first = re.split(r"[。！？\n]", raw)[0].strip()
        if first:
            logline = _clip_nar(first, 80)

    warnings: list[str] = []
    if len(raw) < 8:
        warnings.append("source very short — planner will use vertical beat template")
    if not dialogues:
        warnings.append("no dialogue lines detected — default storyteller VO")

    heat = detect_heat_signals(raw)
    genre_info = detect_genre(raw, heat=heat)
    if heat.get("evidence_max"):
        warnings.append(
            f"adult heat signals → spine={heat.get('spine')} heat_scale={heat.get('heat_scale')}"
        )
    for gw in genre_info.get("warnings", []):
        warnings.append(gw)
    genre = genre_info["genre"]

    return {
        "schema_version": 1,
        "kind": "normalized-story",
        "at": utc_now(),
        "title": title,
        "logline": logline,
        "genre": genre,
        "raw_excerpt": raw[:2000],
        "source_path": source_path,
        "source_chars": len(raw),
        "character_candidates": chars,
        "location_candidates": locs,
        "dialogue_blocks": dialogues,
        "scene_chunks": chunks,
        "vo_mode_suggest": "character" if dialogues else "storyteller",
        "heat_signals": heat,
        "genre_evidence": genre_info["evidence"],
        "warnings": warnings,
        "source_map": {
            "method": "deterministic_v1",
            "note": "Agent may refine; this is structure-only normalize",
        },
    }


def _draft_story_contract(normalized: dict[str, Any]) -> dict[str, Any]:
    """Create an honest story contract; unknown intent stays blank/draft."""
    logline = str(normalized.get("logline") or "")
    genre = str(normalized.get("genre") or "adult")
    return {
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


def structure_episode(
    normalized: dict[str, Any],
    *,
    target_duration: float = 45.0,
    episode_number: int = 1,
) -> dict[str, Any]:
    """episode.structure — single vertical short episode."""
    target_duration = max(12.0, min(180.0, float(target_duration or 45)))
    title = str(normalized.get("title") or "ep")
    logline = str(normalized.get("logline") or "")
    return {
        "id": f"ep{episode_number:02d}",
        "episodeNumber": episode_number,
        "title": title,
        "targetDuration": target_duration,
        "openingHook": logline,
        "centralConflict": AUTHORING_PLACEHOLDER,
        "climax": AUTHORING_PLACEHOLDER,
        "endingHook": AUTHORING_PLACEHOLDER,
        "aspectRatio": "9:16",
        "status": "planning",
        "vo_mode": normalized.get("vo_mode_suggest") or "storyteller",
    }


def _sentences(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", body)
    return [p.strip() for p in parts if p.strip()]


def segment_scenes(
    normalized: dict[str, Any],
    episode: dict[str, Any],
) -> list[dict[str, Any]]:
    """scene.segment"""
    chunks = normalized.get("scene_chunks") or [
        {"title": "Main", "body": normalized.get("raw_excerpt") or ""}
    ]
    locs = normalized.get("location_candidates") or []
    loc_id = locs[0]["id"] if locs else None
    char_ids = [c["id"] for c in (normalized.get("character_candidates") or []) if c.get("id")]

    scenes: list[dict[str, Any]] = []
    for i, ch in enumerate(chunks, start=1):
        if not isinstance(ch, dict):
            continue
        body = str(ch.get("body") or "")
        scenes.append(
            {
                "id": f"sc{i:02d}_{_slug(str(ch.get('title') or f's{i}'), f'sc{i}')}",
                "order": i,
                "title": str(ch.get("title") or f"Scene {i}")[:60],
                "synopsis": _clip_nar(body, 100),
                "body": body,
                "locationId": loc_id,
                "characterIds": char_ids[:4],
                "dramaticPurpose": "advance story",
                "purpose": "",
                "conflict": "",
                "entry_state": "",
                "exit_state": "",
                "emotionalStart": "",
                "emotionalEnd": "",
                "productionMode": "hybrid",
                "status": "planned",
                "targetDuration": None,  # filled after beats
            }
        )
    if not scenes:
        scenes.append(
            {
                "id": "sc01_main",
                "order": 1,
                "title": "Main",
                "synopsis": str(episode.get("openingHook") or ""),
                "body": str(normalized.get("raw_excerpt") or ""),
                "locationId": loc_id,
                "characterIds": char_ids[:4],
                "productionMode": "hybrid",
                "status": "planned",
            }
        )
    return scenes


def _compact_adult_spine_for_scene(body: str) -> list[dict[str, Any]]:
    """Multi-scene adult: one short local arc per scene (no full dual-climax clone)."""
    b = body or ""
    # Map content keywords → local heat arc length 3–5
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
                "objective": "section peak action",
                "importance": "high",
                "weight": 0.35,
                "shots_n": 2,
                "heat_phase": "act",
                "coitus_beat": "rhythm",
                "wardrobe_state": "undressed",
                "duration_boost": 6.0,
            }
        )
        spine.append(
            {
                "key": "button",
                "dramatic_function": "afterglow",
                "objective": "section exit / hook out",
                "importance": "med",
                "weight": 0.2,
                "shots_n": 1,
                "heat_phase": "afterglow",
                "coitus_beat": "hook",
                "wardrobe_state": "partial",
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
    # drop None coitus_beat keys for cleaner graph
    for sp in spine:
        if sp.get("coitus_beat") is None:
            sp.pop("coitus_beat", None)
    return spine


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
    adult = (genre or "adult") == "adult" and (
        bool(heat.get("heat_scale") == "max" or heat.get("hardcore"))
    )
    # Multi-scene user scripts: compact per-scene arc (prevents 3× full adult template)
    if adult and not is_only_scene:
        spine = _compact_adult_spine_for_scene(body)
    else:
        spine = select_beat_spine(
            heat,
            genre=genre,
            target_duration=target_duration or scene_budget_sec,
            multi_scene=not is_only_scene,
        )
    # short scene: fewer beats (only for non-adult genre spines + default drama)
    is_genre_spine = genre and genre != "adult" and genre in GENRE_SPINES
    if not adult:
        if not is_only_scene and len(sents) <= 2:
            # Drop the 2nd beat (setup/context) for short multi-scene
            if len(spine) >= 5:
                spine = [spine[0], spine[2], spine[3], spine[4]]
        elif len(sents) == 1 and is_only_scene:
            spine = list(DEFAULT_BEAT_SPINE) if not is_genre_spine else spine

    # distribute sentences across beats
    if not sents:
        sents = [str(scene.get("synopsis") or scene.get("title") or "画面推进")]

    beats: list[dict[str, Any]] = []
    n = len(spine)
    for bi, sp in enumerate(spine):
        # assign sentence slice
        if n == 1:
            chunk_sents = sents
        else:
            start = int(round(bi * len(sents) / n))
            end = int(round((bi + 1) * len(sents) / n))
            chunk_sents = sents[start:end] or [sents[min(bi, len(sents) - 1)]]
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
            "action": _clip_nar(action_text, 120),
            "outcome": "",
            "emotionalShift": {"from": "", "to": ""},
            "importance": sp["importance"],
            "dramatic_function": sp["dramatic_function"],
            "targetDuration": dur,
            "shots_n": int(sp["shots_n"]),
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
    return beats


def _vertical_composition(order: int, df: str) -> str:
    if df in {"hook", "action"}:
        return "center-subject"
    if df == "sensory":
        return "three-layer-depth" if order % 2 == 0 else "foreground-background"
    if df == "approach":
        return "two-character-stack" if order % 2 == 0 else "center-subject"
    return "center-subject"


def _camera_axis(df: str, idx: int) -> str:
    axes = {
        "hook": "dolly_in",
        "approach": "pan_with",
        "sensory": "low_lean",
        "reaction": "ecu_hold",
        "action": "dolly_in",
        "afterglow": "pull_back",
        "bridge": "locked",
    }
    base = axes.get(df, "dolly_in")
    if idx % 3 == 1 and base == "dolly_in":
        return "ecu_hold"
    return base


def _production_mode(df: str, shot_role: str) -> str:
    if shot_role == "env":
        return "text-to-video"
    if df in {"bridge", "afterglow"}:
        return "panel-animation"
    if df in {"action", "sensory", "hook"}:
        return "single-keyframe-i2v"
    return "single-keyframe-i2v"


def plan_shots(
    beat: dict[str, Any],
    *,
    scene: dict[str, Any],
    shot_counter_start: int,
    character_ids: list[str],
    location_id: str | None,
    chain_continue: bool = True,
) -> list[dict[str, Any]]:
    """shot.plan — expand beat into 1–N vertical shots."""
    n = max(1, min(3, int(beat.get("shots_n") or 1)))
    budget = float(beat.get("targetDuration") or 6)
    per_floor = max(3.0, round(budget / n, 1))
    df = str(beat.get("dramatic_function") or "action")
    if df not in DRAMATIC_FUNCS:
        df = "action"
    source = str(beat.get("source_text") or beat.get("action") or "")
    sents = _sentences(source) or [source]

    shots: list[dict[str, Any]] = []
    coverage_roles_by_beat = {
        "hook": ["establish"],
        "approach": ["context"],
        "sensory": ["action", "reveal"],
        "action": ["decision", "reaction"],
        "afterglow": ["consequence"],
        "bridge": ["context"],
    }
    coverage_roles = coverage_roles_by_beat.get(df, ["action"])
    for i in range(n):
        idx = shot_counter_start + i
        scene_order = int(scene.get("order") or 1)
        beat_order = int(beat.get("order") or 1)
        sid = f"ep01_sc{scene_order:02d}_bt{beat_order:02d}_sh{i + 1:02d}"
        piece = sents[i] if i < len(sents) else sents[-1]
        # second shot in beat: reaction / insert flavor
        local_df = df
        if n > 1 and i == n - 1 and df in {"sensory", "action"}:
            local_df = "reaction"
        shot_role = "hero"
        if local_df == "bridge":
            shot_role = "env"
        chain = "continue" if chain_continue and idx > 1 else ("continue" if idx > 1 else "cut")
        if i == 0 and idx == 1:
            chain = "cut"
        panel_id = f"panel_{sid}_01"
        prod = _production_mode(local_df, shot_role)
        vc = _vertical_composition(idx, local_df)
        axis = _camera_axis(local_df, idx)
        coverage_role = coverage_roles[i % len(coverage_roles)]
        heat_phase = str(beat.get("heat_phase") or "").strip().lower() or ""
        coitus_beat = str(beat.get("coitus_beat") or "").strip().lower() or ""
        wardrobe_state = str(beat.get("wardrobe_state") or "full").strip().lower() or "full"
        # Cinema-grade camera prompt (Seedance camera language bridge, 2026-07-23).
        # Enriches the fixed-enum axis with structured move/shot/angle/pacing/lighting.
        from cinema_prompt import build_camera_prompt as _build_cinema_prompt

        scene_type = str(scene.get("genre") or "").strip().lower() or None
        cinema = _build_cinema_prompt(
            dramatic_function=local_df,
            shot_index=idx,
            heat_phase=heat_phase or None,
            scene_type=scene_type,
            duration_sec=float(beat.get("duration_sec") or 5.0),
        )
        camera_prompt = cinema["camera_prompt"]
        # Adult: coitus-readable action — but keep user text in must_show when present
        adult_actions = {
            "entry": "pin partner entry mount-settle weight drop pelvis aim",
            "undress": "removes dress armor straps slide undress bare shoulders",
            "union": "straddle-seat hips settle pelvis-lock skin-to-skin",
            "rhythm": "hips-sink grind-forward thrust-rhythm twice clutch fabric",
            "lock": "leg-wrap-waist clutch sheets micro-tremor lock",
            "finish": "arch-finish residual-tremor wet eyes body softens",
            "hook": "ear whisper residual hold next round invitation",
        }
        user_piece = str(piece or "").strip()
        if coitus_beat in adult_actions:
            # VO-visual align: action mirrors user verbs when user wrote them
            must_show = adult_actions[coitus_beat]
            if _user_nar_substantive(user_piece):
                must_show = f"{must_show}; story: {_clip_nar(user_piece, 40)}"
            visible_change = must_show
            action_text = must_show
        else:
            must_show = f"{coverage_role}: {_clip_nar(user_piece, 60)}"
            visible_change = {
                "establish": "空间与人物关系可读",
                "context": "人物目标与阻力进入画面",
                "reveal": "新线索或欲望被看见",
                "reaction": "角色反应发生变化",
                "action": "冲突动作完成一步",
                "decision": "角色做出不可撤回的选择",
                "consequence": "动作造成的状态后果",
            }[coverage_role]
            action_text = must_show
        extreme_seed = bool(beat.get("_extreme_seed"))
        # P0 user-source fidelity: never wholesale replace user nar with 展厅模板
        nar = preserve_user_nar(
            user_piece,
            heat_phase=heat_phase,
            coitus_beat=coitus_beat
            if not (coitus_beat == "rhythm" and i > 0)
            else ("rhythm" if i == 0 else "rhythm"),
            extreme_seed=extreme_seed,
            max_chars=48,
        )
        if coitus_beat == "rhythm" and i > 0 and not _user_nar_substantive(user_piece):
            nar = preserve_user_nar(
                "",
                heat_phase=heat_phase,
                coitus_beat="rhythm",
                extreme_seed=extreme_seed,
                max_chars=48,
            )
            if extreme_seed:
                nar = _clip_nar("换姿再沉腰。夹紧，不许退。", 48)
            else:
                nar = _clip_nar("再沉腰。节奏是她给的。", 48)
        # Multi-pose: rotate sex_pose by coitus beat + index
        pose_cycle = {
            "entry": "wall_pin",
            "undress": "lap_grind",
            "union": "straddle",
            "rhythm": "cowgirl" if i == 0 else "from_behind",
            "lock": "lotus",
            "finish": "missionary_pin",
            "hook": "side_entry",
        }
        sex_pose = pose_cycle.get(coitus_beat) or ""
        # Act/climax plates: longer floor so sex duration ratio hits ≥20%/40%
        floor = per_floor
        if heat_phase in {"act", "climax"}:
            floor = max(per_floor, 8.0)
        elif heat_phase == "foreplay":
            floor = max(per_floor, 5.0)
        per = _duration_for_nar(nar, floor=floor)
        # Size ladder: setup wide → act medium → climax CU → lock insert
        # Size ladder pressure: avoid 3× same rank in a row (SIZE_STACK_FLAT)
        if coitus_beat == "entry" and heat_phase == "setup":
            shot_size = "medium full"
        elif coitus_beat == "undress":
            shot_size = "medium"
        elif coitus_beat == "entry":
            shot_size = "close-up"  # foreplay pressure
        elif coitus_beat == "union":
            shot_size = "medium"
        elif coitus_beat == "rhythm":
            shot_size = "medium" if i == 0 else "close-up"
        elif coitus_beat == "lock":
            shot_size = "close-up insert fabric hands"
        elif coitus_beat == "finish":
            shot_size = "close-up"
        elif coitus_beat == "hook":
            shot_size = "medium"
        else:
            shot_size = "close-up" if local_df in {"hook", "reaction", "action"} else "medium"
        motion_by_cb = {
            "entry": "pin seat weight drop mount-settle low angle",
            "undress": "straps slide dress peels bare skin expands",
            "union": "straddle-seat hips settle pelvis-lock weight down",
            "rhythm": "hips-sink twice grind-forward thrust-rhythm locked camera",
            "lock": "leg-wrap-waist clutch sheets micro-tremor",
            "finish": "arch-finish residual-tremor static hold",
            "hook": "lean to ear residual pull-back hold",
        }
        motion = motion_by_cb.get(coitus_beat) or axis.replace("_", " ")
        char_ids = list(character_ids[:2]) or ["hero"]
        subject = f"vertical 9:16, adult {char_ids[0] if char_ids else 'hero'}"
        if wardrobe_state in {"partial", "undressed", "bare"}:
            subject += f" {wardrobe_state} bare skin readable"
        # Derive multi-axis character states (hair, skin, arousal, wardrobe)
        c_hair = "neat"
        c_skin = "normal"
        c_arousal = "calm"
        if heat_phase in {"act", "climax"}:
            c_hair = "disheveled"
            c_skin = "glistening_sweat"
            c_arousal = "climax_ecstasy" if heat_phase == "climax" else "heavy_breathing"
        elif heat_phase == "foreplay":
            c_hair = "slightly_moussed"
            c_skin = "flushed"
            c_arousal = "heavy_breathing"
        elif heat_phase == "afterglow":
            c_hair = "sweat_moistened_strands"
            c_skin = "afterglow_blush"
            c_arousal = "calm"
        character_states = {
            "wardrobe": wardrobe_state,
            "hair": c_hair,
            "skin": c_skin,
            "arousal": c_arousal,
        }

        film_dsl: dict[str, Any] = {
            "subject": subject,
            "action": action_text,
            "motion": motion,
            "camera_axis": axis,
            "camera_prompt": camera_prompt,
            "visible_change": visible_change,
            "story_beat": str(beat.get("objective") or local_df),
            "start_pose": (
                f"already {wardrobe_state} from prior undress"
                if wardrobe_state in {"partial", "undressed", "bare"}
                else "enter beat"
            ),
            "end_pose": "exit beat — feeds next",
            "chain_mode": chain,
            "cut_on": "mid_motion" if chain == "continue" else "fresh",
            "cast": char_ids,
            "viewpoint": "objective",
            "look_axis": "center",
            "camera": {
                "shot_size": shot_size,
                "angle": "slight low"
                if coitus_beat in {"union", "rhythm", "entry"}
                else "eye_level",
            },
            "wardrobe_state": wardrobe_state,
            "character_states": character_states,
        }
        if heat_phase:
            film_dsl["heat_phase"] = heat_phase
        if coitus_beat:
            film_dsl["coitus_beat"] = coitus_beat
        if sex_pose:
            film_dsl["sex_pose"] = sex_pose
        shots.append(
            {
                "id": sid,
                "order": idx,
                "filmSpecShotId": sid,
                "beatId": beat["id"],
                "beat_id": beat["id"],
                "narrativePurpose": str(beat.get("objective") or local_df),
                "dramaticFunction": local_df,
                "shotSize": shot_size,
                "verticalComposition": vc,
                "cameraMovement": axis,
                "productionMode": prod,
                "targetDuration": per,
                "characterIds": char_ids,
                "locationId": location_id,
                "wardrobeState": wardrobe_state,
                "characterStates": character_states,
                "character_states": character_states,
                "heatPhase": heat_phase,
                "coitusBeat": coitus_beat,
                "sexPose": sex_pose,
                "chainMode": chain,
                "coverage_role": coverage_role,
                "must_show": must_show,
                "visible_change": visible_change,
                "start_state": AUTHORING_PLACEHOLDER,
                "end_state": AUTHORING_PLACEHOLDER,
                "playable_action": action_text if coitus_beat else AUTHORING_PLACEHOLDER,
                "expectation": AUTHORING_PLACEHOLDER,
                "subtext": AUTHORING_PLACEHOLDER,
                "gaze_target": AUTHORING_PLACEHOLDER,
                "reaction_trigger": AUTHORING_PLACEHOLDER,
                "body_state": wardrobe_state,
                "source_refs": [beat.get("id")],
                "nar": nar,
                "panelIds": [panel_id],
                "keyframeIds": [],
                "motionClipIds": [],
                "dialogueLineIds": [f"dlg_{sid}"],
                "panels": [
                    {
                        "id": panel_id,
                        "order": 1,
                        "subject": char_ids[0] if char_ids else "hero",
                        "action": must_show,
                        "expression": AUTHORING_PLACEHOLDER,
                        "location": location_id or "",
                        "verticalComposition": vc,
                        "cameraAngle": "eye_level",
                        "lighting": "",
                        "style": "vertical drama comic",
                        "continuityConstraints": [f"chain_mode={chain}"],
                        "negativeConstraints": [
                            "no landscape crop",
                            "no horizontal storyboard paste",
                        ],
                        "referenceAssetIds": [],
                        "sourcePromptPath": None,
                        "must_include": [must_show],
                        "playable_action": AUTHORING_PLACEHOLDER,
                        "gaze_target": AUTHORING_PLACEHOLDER,
                    }
                ],
                "assetHints": {
                    "keyframePath": None,
                    "clipPath": None,
                    "promptPath": None,
                    "hasKeyframe": False,
                    "hasClip": False,
                    "hasPrompt": False,
                },
                "_film": {
                    "title": _clip_nar(str(beat.get("objective") or sid), 24),
                    "shot_role": shot_role,
                    "dramatic_function": local_df,
                    "duration_sec": per,
                    "nar": nar,
                    "beat_id": beat["id"],
                    "heat_phase": heat_phase or None,
                    "coitus_beat": coitus_beat or None,
                    "sex_pose": sex_pose or None,
                    "wardrobe_state": wardrobe_state,
                    "dsl": film_dsl,
                },
            }
        )
    return shots


def build_planned_graph(
    normalized: dict[str, Any],
    *,
    target_duration: float = 45.0,
    root: Path | None = None,
) -> dict[str, Any]:
    """Full plan: normalize → episode → scenes → beats → shots → graph."""
    # Adult briefs need longer plate so act+climax can hit ≥20%/40%
    heat = (
        normalized.get("heat_signals") if isinstance(normalized.get("heat_signals"), dict) else {}
    )
    if heat.get("dual_climax") and target_duration < 90:
        target_duration = 100.0
    elif heat.get("hardcore") and target_duration < 60:
        target_duration = 60.0
    elif heat.get("heat_scale") == "max" and target_duration < 50:
        target_duration = 55.0
    episode = structure_episode(normalized, target_duration=target_duration)
    scenes = segment_scenes(normalized, episode)
    total = float(episode["targetDuration"])
    # weight scenes equally (or by body length)
    weights = []
    for sc in scenes:
        w = max(1, len(str(sc.get("body") or "")))
        weights.append(w)
    wsum = sum(weights) or 1
    char_ids = [c["id"] for c in (normalized.get("character_candidates") or []) if c.get("id")]
    if not char_ids:
        char_ids = ["hero"]

    shot_i = 1
    scenes_out: list[dict[str, Any]] = []
    for si, sc in enumerate(scenes):
        budget = total * (weights[si] / wsum)
        sc["targetDuration"] = round(budget, 1)
        beats = extract_beats(
            sc,
            scene_budget_sec=budget,
            is_only_scene=len(scenes) == 1,
            heat=heat,
            target_duration=total,
            genre=normalized.get("genre"),
        )
        if heat.get("hardcore") or heat.get("dual_climax"):
            for bt in beats:
                bt["_extreme_seed"] = True
        beats_out: list[dict[str, Any]] = []
        for bt in beats:
            shots = plan_shots(
                bt,
                scene=sc,
                shot_counter_start=shot_i,
                character_ids=char_ids,
                location_id=sc.get("locationId"),
                chain_continue=True,
            )
            shot_i += len(shots)
            bt_out = {
                "id": bt["id"],
                "order": bt["order"],
                "objective": bt["objective"],
                "action": bt["action"],
                "outcome": bt.get("outcome") or "",
                "obstacle": bt.get("obstacle") or AUTHORING_PLACEHOLDER,
                "tactic": bt.get("tactic") or AUTHORING_PLACEHOLDER,
                "turn": bt.get("turn") or AUTHORING_PLACEHOLDER,
                "state_delta": bt.get("state_delta") or AUTHORING_PLACEHOLDER,
                "audience_question": bt.get("audience_question") or AUTHORING_PLACEHOLDER,
                "emotional_turn": bt.get("emotional_turn") or AUTHORING_PLACEHOLDER,
                "authoring_questions": list(bt.get("authoring_questions") or []),
                "emotionalShift": bt.get("emotionalShift") or {"from": "", "to": ""},
                "importance": bt["importance"],
                "targetDuration": bt["targetDuration"],
                "director_board": draft_director_board(),
                "shots": shots,
            }
            beats_out.append(bt_out)
        sc_out = {
            "id": sc["id"],
            "order": sc["order"],
            "title": sc["title"],
            "synopsis": sc.get("synopsis") or "",
            "locationId": sc.get("locationId"),
            "characterIds": sc.get("characterIds") or char_ids,
            "targetDuration": sc.get("targetDuration"),
            "productionMode": sc.get("productionMode") or "hybrid",
            "status": "planned",
            "beats": beats_out,
        }
        scenes_out.append(sc_out)

    episode_out = {
        **episode,
        "scenes": scenes_out,
        "status": "planning",
    }

    characters = []
    for c in normalized.get("character_candidates") or []:
        if not isinstance(c, dict):
            continue
        role = str(c.get("role") or "supporting")
        is_lead = role in ("lead", "speaking")
        characters.append(
            {
                "id": c.get("id"),
                "identity": c.get("name") or c.get("id"),
                "name": c.get("name") or c.get("id"),
                "age": "",
                "personality": "",
                "want": AUTHORING_PLACEHOLDER if is_lead else "",
                "need": AUTHORING_PLACEHOLDER if is_lead else "",
                "flaw": "",
                "ghost_wound": "",
                "arc_turning_points": [],
                "relationships": [],
                "psych_markers": [],
                "dramatic_role": "protagonist" if role == "lead" else "supporting",
                "defaultWardrobe": "",
                "castMaster": None,
            }
        )
    locations = [
        {"id": x.get("id"), "description": x.get("description") or ""}
        for x in (normalized.get("location_candidates") or [])
        if isinstance(x, dict)
    ]

    root_s = str(root) if root else ""
    graph = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "kind": "vertical-drama-graph",
        "derived_from": {
            "film_spec": None,
            "style_bible": None,
            "at": utc_now(),
            "mode": "planned",
            "planner": "story_plan.v2",
            "normalized_title": normalized.get("title"),
        },
        "project": {
            "id": _slug(str(normalized.get("title") or "project"), "project"),
            "title": str(normalized.get("title") or "untitled"),
            "aspectRatio": "9:16",
            "targetResolution": "1080x1920",
            "targetFps": 30,
            "root": root_s,
        },
        "episodes": [episode_out],
        "story": _draft_story_contract(normalized),
        "characters": characters,
        "locations": locations,
        "props": [],
        "warnings": list(normalized.get("warnings") or []),
    }
    ensure_graph_controls(graph)
    graph["content_sha256"] = graph_content_sha256(graph)
    return graph


def stabilize_shot_ids(
    new_graph: dict[str, Any], previous_graph: dict[str, Any] | None
) -> dict[str, Any]:
    """Reuse prior shot ids by semantic slot, not by array position."""
    if not isinstance(previous_graph, dict):
        return new_graph
    old_slots: dict[tuple[str, str], str] = {}
    for ep in previous_graph.get("episodes") or []:
        for sc in (ep.get("scenes") or []) if isinstance(ep, dict) else []:
            for bt in (sc.get("beats") or []) if isinstance(sc, dict) else []:
                if not isinstance(bt, dict):
                    continue
                bid = str(bt.get("id") or "")
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    sid = str(sh.get("id") or "")
                    role = str(sh.get("coverage_role") or "")
                    if bid and sid and role:
                        old_slots[(bid, role)] = sid

    used: set[str] = set()
    for ep in new_graph.get("episodes") or []:
        for sc in (ep.get("scenes") or []) if isinstance(ep, dict) else []:
            for bt in (sc.get("beats") or []) if isinstance(sc, dict) else []:
                if not isinstance(bt, dict):
                    continue
                bid = str(bt.get("id") or "")
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    old_id = old_slots.get((bid, str(sh.get("coverage_role") or "")))
                    sid = old_id if old_id and old_id not in used else str(sh.get("id") or "")
                    used.add(sid)
                    old_sid = str(sh.get("id") or "")
                    if sid != old_sid:
                        sh["id"] = sid
                        sh["filmSpecShotId"] = sid
                        sh["panelIds"] = [
                            str(x).replace(old_sid, sid) for x in (sh.get("panelIds") or [])
                        ]
                        for panel in sh.get("panels") or []:
                            if isinstance(panel, dict):
                                panel["id"] = str(panel.get("id") or "").replace(old_sid, sid)
                    for panel in sh.get("panels") or []:
                        if isinstance(panel, dict):
                            panel["sourcePromptPath"] = None
    return new_graph


def project_graph_to_film_spec(
    graph: dict[str, Any],
    *,
    base_spec: dict[str, Any] | None = None,
    normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project planned graph → film-spec scenes/shots (executable)."""
    base = dict(base_spec or {})
    ep = (graph.get("episodes") or [{}])[0]
    if not isinstance(ep, dict):
        ep = {}
    title = str(
        graph.get("project", {}).get("title") or ep.get("title") or base.get("title") or "untitled"
    )
    logline = str(ep.get("openingHook") or (normalized or {}).get("logline") or title)
    vo_mode = str((normalized or {}).get("vo_mode_suggest") or base.get("vo_mode") or "storyteller")
    if vo_mode not in {"storyteller", "character", "hybrid"}:
        vo_mode = "storyteller"

    cast_ids = [
        c.get("id") for c in (graph.get("characters") or []) if isinstance(c, dict) and c.get("id")
    ]
    if not cast_ids:
        cast_ids = ["hero"]

    scenes_fs: list[dict[str, Any]] = []
    for sc in ep.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        shots_fs: list[dict[str, Any]] = []
        for bt in sc.get("beats") or []:
            if not isinstance(bt, dict):
                continue
            for sh in bt.get("shots") or []:
                if not isinstance(sh, dict):
                    continue
                film = sh.get("_film") if isinstance(sh.get("_film"), dict) else {}
                dsl = film.get("dsl") if isinstance(film.get("dsl"), dict) else {}
                if not dsl:
                    dsl = {
                        "subject": "vertical 9:16 subject",
                        # nar is audio text, never an automatic instruction for
                        # character movement.  Author a visible action separately.
                        "action": sh.get("must_show") or "needs_authoring",
                        "motion": sh.get("cameraMovement") or "dolly_in",
                        "camera_axis": sh.get("cameraMovement") or "dolly_in",
                        "visible_change": sh.get("visible_change") or "needs_authoring",
                        "story_beat": sh.get("narrativePurpose") or "",
                        "chain_mode": sh.get("chainMode") or "continue",
                        "cast": sh.get("characterIds") or cast_ids[:1],
                    }
                shot_obj: dict[str, Any] = {
                    "id": sh.get("id") or sh.get("filmSpecShotId"),
                    "title": film.get("title") or sh.get("narrativePurpose") or sh.get("id"),
                    "shot_role": film.get("shot_role") or "hero",
                    "dramatic_function": film.get("dramatic_function")
                    or sh.get("dramaticFunction")
                    or "action",
                    "duration_sec": float(
                        film.get("duration_sec") or sh.get("targetDuration") or 5
                    ),
                    "nar": film.get("nar") or sh.get("nar") or "……",
                    "beat_id": film.get("beat_id") or sh.get("beatId"),
                    "coverage_role": sh.get("coverage_role") or "",
                    "must_show": sh.get("must_show") or "",
                    "visible_change": sh.get("visible_change") or "",
                    "start_state": sh.get("start_state") or "",
                    "end_state": sh.get("end_state") or "",
                    "playable_action": sh.get("playable_action") or "",
                    "expectation": sh.get("expectation") or "",
                    "subtext": sh.get("subtext") or "",
                    "gaze_target": sh.get("gaze_target") or "",
                    "reaction_trigger": sh.get("reaction_trigger") or "",
                    "body_state": sh.get("body_state") or "",
                    "source_refs": list(sh.get("source_refs") or []),
                    "production_mode": sh.get("productionMode"),
                    "vertical_composition": sh.get("verticalComposition"),
                    "lipsync": False,
                    "dsl": dsl,
                }
                hp = film.get("heat_phase") or sh.get("heatPhase")
                if hp:
                    shot_obj["heat_phase"] = hp
                cb = film.get("coitus_beat") or sh.get("coitusBeat")
                if cb:
                    shot_obj["coitus_beat"] = cb
                sp = film.get("sex_pose") or sh.get("sexPose")
                if sp:
                    shot_obj["sex_pose"] = sp
                    if isinstance(dsl, dict) and not dsl.get("sex_pose"):
                        dsl["sex_pose"] = sp
                ws = film.get("wardrobe_state") or sh.get("wardrobeState")
                if ws:
                    shot_obj["wardrobe_state"] = ws
                    if isinstance(dsl, dict) and not dsl.get("wardrobe_state"):
                        dsl["wardrobe_state"] = ws
                shots_fs.append(shot_obj)
        scenes_fs.append(
            {
                "title": sc.get("title") or "Scene",
                "summary": sc.get("synopsis") or "",
                "shots": shots_fs,
            }
        )

    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}
    emotional = [str(x) for x in (story.get("emotional_arc") or []) if str(x).strip()]
    if len(emotional) < 3:
        emotional = [
            str(ep.get("openingHook") or ""),
            str(ep.get("climax") or ""),
            str(ep.get("endingHook") or ""),
        ]

    base_di = base.get("director_intent") if isinstance(base.get("director_intent"), dict) else {}
    logline_full = logline if len(logline) >= 8 else (logline + " ——竖屏漫剧。")
    taboos = base_di.get("taboos") if isinstance(base_di.get("taboos"), list) else None
    if not taboos:
        taboos = ["横屏分镜硬裁", "无钩子开场"]

    heat = (
        (normalized or {}).get("heat_signals")
        if isinstance((normalized or {}).get("heat_signals"), dict)
        else {}
    )
    di: dict[str, Any] = {
        **base_di,
        "premise": story.get("premise") or base_di.get("premise") or "",
        "logline": logline_full,
        "tone": base_di.get("tone") or story.get("theme") or "竖屏漫剧",
        "emotional_arc": emotional,
        "theme": base_di.get("theme") or story.get("theme") or "",
        "audience": base_di.get("audience") or "竖屏短视频",
        "cast": cast_ids,
        "taboos": taboos,
        "protagonist_goal": story.get("protagonist_goal") or "",
        "protagonist_want": story.get("protagonist_want") or "",
        "protagonist_need": story.get("protagonist_need") or "",
        "protagonist_arc": story.get("protagonist_arc") or "",
        "opposition": story.get("opposition") or "",
        "stakes": story.get("stakes") or "",
        "climax_choice": story.get("climax_choice") or "",
        "ending_hook": story.get("ending_hook") or "",
    }
    # P0-2: project act_structure + pace_chart from story contract
    if story.get("act_structure") and not di.get("act_structure"):
        di["act_structure"] = story["act_structure"]
    if story.get("pace_chart") and not di.get("pace_chart"):
        di["pace_chart"] = story["pace_chart"]
    if heat.get("audience_profile"):
        di["audience_profile"] = heat["audience_profile"]
        di["audience"] = di.get("audience") or "重口男向短片观众"
        di["tone"] = di.get("tone") if base_di.get("tone") else "成人重口·办事完成·荤梗拉满"
    elif heat.get("heat_scale") == "max":
        di["tone"] = di.get("tone") if base_di.get("tone") else "成人色气·办事完成可说满"
        di["audience"] = di.get("audience") if base_di.get("audience") else "成人短片观众"

    # Seed coitus_grammar.beats from projected shots
    coitus_beats: dict[str, list[str]] = {}
    for sc in scenes_fs:
        for sh in sc.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            cb = str(sh.get("coitus_beat") or "").strip().lower()
            sid = str(sh.get("id") or "")
            if cb and sid:
                coitus_beats.setdefault(cb, []).append(sid)

    spec: dict[str, Any] = {
        **base,
        "title": title,
        "description": logline,
        "aspect_ratio": "9:16",
        "genre": story.get("genre") or (normalized or {}).get("genre") or "adult",
        "vo_mode": vo_mode,
        "tts_backend": base.get("tts_backend") or "edge",
        "i2v_provider": base.get("i2v_provider") or "grok",
        "caption_mode": base.get("caption_mode") or "zh",
        "director_intent": di,
        "scenes": scenes_fs,
        "_plan": {
            "source": "story_plan.v1",
            "at": utc_now(),
            "episode_id": ep.get("id"),
            "target_duration": ep.get("targetDuration"),
            "graph_mode": (graph.get("derived_from") or {}).get("mode"),
            "heat_spine": heat.get("spine") or "default",
            "genre": story.get("genre") or (normalized or {}).get("genre") or "adult",
        },
        "_projection": {
            "source": "drama-graph.json",
            "source_revision": int(graph.get("revision") or 1),
            "source_sha256": graph_content_sha256(graph),
            "generated_at": utc_now(),
            "state": graph.get("state") or "draft",
        },
    }
    # Keep user source on film-spec for fidelity gate + agent rewrites
    raw_ex = str((normalized or {}).get("raw_excerpt") or "").strip()
    if raw_ex:
        spec["source_excerpt"] = raw_ex[:4000]
        spec["user_source_fidelity_strict"] = True
    if heat.get("heat_scale"):
        spec["heat_scale"] = heat["heat_scale"]
        spec["heat_phase_auto"] = True
        spec["sex_floor_strict"] = True
        spec["sex_wardrobe_strict"] = True
        spec["sex_vo_strict"] = True
        spec["spice_level"] = "extreme" if heat.get("hardcore") else "explicit"
        if heat.get("hardcore"):
            spec["sex_min_duration_ratio"] = 0.40
            spec["coitus_strict"] = True
            spec["size_ladder_strict"] = True
            spec["montage_strict"] = True
            spec["pose_strict"] = True
            spec["sex_vo_motion_strict"] = True
            spec["audience_profile"] = "hardcore_male"
        else:
            # max adult: sex floor product 30% (overrideable)
            if spec.get("sex_min_duration_ratio") is None:
                spec["sex_min_duration_ratio"] = 0.30
        if coitus_beats:
            spec["coitus_grammar"] = {
                "enabled": True,
                "mute_frame_test": True,
                "beats": coitus_beats,
            }
    return spec


def seed_style_bible_from_normalized(
    root: Path,
    normalized: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Light-touch character/location seed into style-bible (never unlock Approved)."""
    root = Path(root)
    path = root / "style-bible.json"
    bible = read_json(path) or {"schema_version": 2, "locked": False}
    if bible.get("locked") or str(bible.get("state") or "").lower() == "approved":
        if not force:
            return {"ok": True, "skipped": True, "reason": "bible locked"}
    chars = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
    for c in normalized.get("character_candidates") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        cid = str(c["id"])
        if cid in chars and not force:
            continue
        chars[cid] = {
            "identity": str(c.get("name") or cid),
            "default_wardrobe": "",
            "cast_master": chars.get(cid, {}).get("cast_master")
            if isinstance(chars.get(cid), dict)
            else None,
        }
    bible["characters"] = chars
    locs = bible.get("locations") if isinstance(bible.get("locations"), dict) else {}
    for loc in normalized.get("location_candidates") or []:
        if not isinstance(loc, dict) or not loc.get("id"):
            continue
        lid = str(loc["id"])
        if lid not in locs or force:
            locs[lid] = str(loc.get("description") or lid)
    bible["locations"] = locs
    if not bible.get("title"):
        bible["title"] = normalized.get("title")
    bible["schema_version"] = bible.get("schema_version") or 2
    bible["updated_at"] = utc_now()
    write_json(path, bible)
    return {
        "ok": True,
        "skipped": False,
        "characters": list(chars.keys()),
        "locations": list(locs.keys()),
    }


def _ensure_film_root_skeleton(root: Path, *, title: str, theme: str) -> None:
    """Create dirs + minimal manifest so write-spec works without prior init."""
    for sub in (
        "receipts",
        "prompts",
        "keyframes",
        "clips",
        "canonical/cast",
        "canonical/lookbook",
        "selects",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
    man_path = root / "manifest.json"
    if not man_path.is_file():
        write_json(
            man_path,
            {
                "schema_version": 1,
                "provider_default": "grok-imagine",
                "title": title,
                "theme": theme,
                "aspect_ratio": "9:16",
                "width": 720,
                "height": 1280,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "style_locked": False,
                "stills": {},
                "clips": {},
                "gates": {
                    "brief": True,
                    "style": False,
                    "spec": False,
                    "stills": False,
                    "motion": False,
                    "assembly": False,
                    "final": False,
                },
                "outputs": {},
                "notes": ["Created by aifilm plan run (Phase 3)"],
            },
        )


def run_plan(
    root: Path,
    raw: str,
    *,
    title: str | None = None,
    target_duration: float = 45.0,
    apply_film_spec: bool = True,
    force: bool = False,
    source_path: str | None = None,
    seed_bible: bool = True,
) -> dict[str, Any]:
    """End-to-end Phase 3 planner for a film root."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    normalized = normalize_story(raw, title_hint=title, source_path=source_path)
    _ensure_film_root_skeleton(
        root,
        title=str(normalized.get("title") or "untitled"),
        theme=str(normalized.get("logline") or "")[:200],
    )
    write_json(root / "receipts" / "story-normalize.json", normalized)

    previous_graph = read_json(root / "drama-graph.json") or None
    graph = build_planned_graph(normalized, target_duration=target_duration, root=root)
    graph = stabilize_shot_ids(graph, previous_graph)
    if root:
        graph["project"]["root"] = str(root)

    from drama_graph import GRAPH_NAME, validate_graph

    write_json(root / GRAPH_NAME, graph)
    v = validate_graph(graph)
    narrative = validate_narrative_graph(graph)
    write_json(
        root / "receipts" / "drama-graph-plan.json",
        {
            "ok": bool(v.get("ok")),
            "at": utc_now(),
            "mode": "planned",
            "shot_count": v.get("shot_count"),
            "errors": v.get("errors"),
            "warnings": (graph.get("warnings") or []) + (v.get("warnings") or []),
            "narrative": narrative,
            "state": graph.get("state"),
            "content_sha256": graph.get("content_sha256"),
        },
    )

    bible_report = None
    if seed_bible:
        bible_report = seed_style_bible_from_normalized(root, normalized, force=force)

    assets_report: dict[str, Any] | None = None

    spec_report: dict[str, Any] | None = None
    if not apply_film_spec:
        existing = read_json(root / "film-spec.json") or {}
        has_existing_shots = any(
            isinstance(sc, dict) and sc.get("shots") for sc in (existing.get("scenes") or [])
        )
        if has_existing_shots:
            spec_report = {
                "ok": True,
                "skipped": True,
                "reason": "draft-only run preserved existing film-spec; pass --apply-film-spec --force to overwrite",
            }
    if apply_film_spec:
        existing = read_json(root / "film-spec.json") or {}
        has_shots = False
        for sc in existing.get("scenes") or []:
            if isinstance(sc, dict) and sc.get("shots"):
                has_shots = True
                break
        if has_shots and not force:
            spec_report = {
                "ok": False,
                "skipped": True,
                "reason": "film-spec already has shots; pass --force to overwrite plan projection",
            }
        else:
            spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=normalized)
            write_json(root / "film-spec.json", spec)
            # seed timeline
            shots_flat = []
            for sc in spec.get("scenes") or []:
                for sh in sc.get("shots") or []:
                    if isinstance(sh, dict) and sh.get("id"):
                        shots_flat.append(sh)
            timeline = {
                "schema_version": 1,
                "fps": 30,
                "width": 720,
                "height": 1280,
                "shots": [
                    {
                        "id": s["id"],
                        "duration_sec": float(s.get("duration_sec") or 5),
                        "title": s.get("title") or s["id"],
                    }
                    for s in shots_flat
                ],
            }
            write_json(root / "timeline.json", timeline)
            # brief
            brief = read_json(root / "brief.json") or {}
            brief.update(
                {
                    "title": spec.get("title"),
                    "theme": (normalized.get("logline") or "")[:200],
                    "aspect_ratio": "9:16",
                    "planned_at": utc_now(),
                    "plan_source": "story_plan.v1",
                }
            )
            write_json(root / "brief.json", brief)
            spec_report = {
                "ok": True,
                "draft": True,
                "ready_for_media": bool(narrative.get("ok"))
                and all(
                    scope in (graph.get("lock_scopes") or [])
                    for scope in ("story", "beats", "shots", "panels")
                ),
                "shot_count": len(shots_flat),
                "scene_count": len(spec.get("scenes") or []),
                "path": str(root / "film-spec.json"),
                "note": "Run aifilm write-spec --root to validate + inject prompts",
            }

    # Phase 4: structure assets + CharacterState timeline after film-spec exists
    if apply_film_spec and (spec_report or {}).get("ok"):
        try:
            from asset_registry import sync_assets

            assets_report = sync_assets(root, write=True, force=force, update_graph=True)
        except Exception as exc:  # noqa: BLE001
            assets_report = {"ok": False, "error": str(exc)[:200]}

    # count tree
    from drama_graph import graph_status

    # Asset sync may add non-creative graph metadata; refresh the canonical
    # hash and bind the draft projection to the final graph snapshot.
    latest_graph = read_json(root / GRAPH_NAME) or graph
    ensure_graph_controls(latest_graph)
    write_json(root / GRAPH_NAME, latest_graph)
    if (root / "film-spec.json").is_file():
        latest_spec = read_json(root / "film-spec.json") or {}
        projection = (
            latest_spec.get("_projection")
            if isinstance(latest_spec.get("_projection"), dict)
            else {}
        )
        projection.update(
            {
                "source": GRAPH_NAME,
                "source_revision": latest_graph.get("revision"),
                "source_sha256": graph_content_sha256(latest_graph),
                "generated_at": utc_now(),
                "state": latest_graph.get("state") or "draft",
            }
        )
        latest_spec["_projection"] = projection
        write_json(root / "film-spec.json", latest_spec)
    st = graph_status(root, auto_derive=False)

    write_json(
        root / "receipts" / "plan.json",
        {
            "ok": bool(v.get("ok")),
            "at": utc_now(),
            "title": normalized.get("title"),
            "target_duration": target_duration,
            "validate": v,
            "narrative": narrative,
            "film_spec": spec_report,
            "bible": bible_report,
            "assets": assets_report,
            "graph_line": st.get("line"),
        },
    )

    return {
        "ok": bool(v.get("ok")),
        "draft": True,
        "ready_for_projection": bool(narrative.get("ok"))
        and all(
            scope in (latest_graph.get("lock_scopes") or [])
            for scope in ("story", "beats", "shots", "panels")
        ),
        "root": str(root),
        "title": normalized.get("title"),
        "logline": normalized.get("logline"),
        "authoring_questions": _authoring_questions(latest_graph),
        "normalized_path": str(root / "receipts" / "story-normalize.json"),
        "graph_path": str(root / GRAPH_NAME),
        "validate": v,
        "narrative": narrative,
        "counts": st.get("counts"),
        "line": st.get("line"),
        "film_spec": spec_report,
        "bible": bible_report,
        "assets": assets_report,
        "warnings": (normalized.get("warnings") or []) + (v.get("warnings") or []),
        "next": [
            f'aifilm write-spec --root "{root}"',
            f'aifilm assets check --root "{root}"',
            f'aifilm graph status --root "{root}" --with-jobs',
            f'aifilm dispatch --root "{root}"',
        ],
    }


def _authoring_questions(graph: dict[str, Any]) -> list[dict[str, str]]:
    """Return actionable director questions without pretending a draft is locked."""
    questions: list[dict[str, str]] = []
    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}
    for field, question in (
        ("protagonist_goal", "主角想要什么？"),
        ("opposition", "谁或什么阻止主角？"),
        ("stakes", "失败的代价是什么？"),
        ("climax_choice", "本集的关键选择是什么？"),
        ("ending_hook", "结尾留下什么未解决问题？"),
    ):
        if (
            not str(story.get(field) or "").strip()
            or str(story.get(field)) == AUTHORING_PLACEHOLDER
        ):
            questions.append({"node_ref": "story", "field": field, "question": question})
    for ep in graph.get("episodes") or []:
        for sc in ep.get("scenes") or []:
            for bt in sc.get("beats") or []:
                bid = str(bt.get("id") or "beat")
                for field, question in (
                    ("obstacle", "谁或什么阻止这个 Beat 的目标？"),
                    ("tactic", "主角用什么可演出的策略推进？"),
                    ("turn", "什么事件改变这个 Beat 的局面？"),
                    ("outcome", "Beat 结束时产生什么结果？"),
                    ("state_delta", "人物、关系、信息或道具发生什么状态变化？"),
                ):
                    if (
                        not str(bt.get(field) or "").strip()
                        or str(bt.get(field)) == AUTHORING_PLACEHOLDER
                    ):
                        questions.append({"node_ref": bid, "field": field, "question": question})
    return questions


def plan_status(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    norm = read_json(root / "receipts" / "story-normalize.json")
    plan = read_json(root / "receipts" / "plan.json")
    from drama_graph import graph_status

    st = graph_status(root, auto_derive=False)
    from narrative_control import control_status

    return {
        "ok": True,
        "root": str(root),
        "has_normalize": bool(norm),
        "has_plan_receipt": bool(plan),
        "title": (norm or {}).get("title") or (plan or {}).get("title"),
        "graph": st,
        "control": control_status(root),
        "plan_receipt": plan,
    }
