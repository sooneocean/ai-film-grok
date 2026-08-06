#!/usr/bin/env python3
"""Phase 3: story.normalize → episode/scene/beat/shot planning.

Deterministic structure planner for vertical (9:16) drama.
Does NOT call external LLMs — Agent may refine nar/dsl after plan run.
Produces drama-graph.json (planned) + optional film-spec seed.
"""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any

from beat_extraction import (  # noqa: F401  — public re-exports for tests/API
    _GENRE_MARKERS,
    AUTHORING_PLACEHOLDER,
    GENRE_NAMES,
    GENRES,
    _compact_adult_spine_for_scene,
    _sentences,
    extract_beats,
    rebalance_adult_beat_durations,
    select_beat_spine,
)
from dialogue_broll import default_dialogue_broll
from narrative_control import (
    GRAPH_SCHEMA_VERSION,
    draft_director_board,
    ensure_graph_controls,
    graph_content_sha256,
    validate_narrative_graph,
)
from shot_planning import DRAMATIC_FUNCS, plan_shots  # noqa: F401  (re-export)
from story_contract import draft_story_contract as _draft_story_contract
from util import FilmError, read_json, utc_now, write_json

# Beat extraction + story contract live in dedicated modules; re-export for
# public API / tests (GENRES, extract_beats, select_beat_spine, …).

# film-spec dramatic_function enum — re-exported from shot_planning for backward compatibility
# (defined in shot_planning.py to avoid circular import with story_plan.py)

# film-spec dramatic_function enum
# Beat spines are now loaded from JSON files in schemas/beat-spines/
# via beat_spine.load_spine(). See schemas/beat-spines/ for available spines.

# Minimal machine-readable defaults used by hard-default contract consumers.
# Full projects receive their complete spec from ``run_plan``.
DEFAULT_SPEC: dict[str, Any] = {"sex_floor_strict": True}

# ``schema_version`` describes the normalized-story receipt and remains stable
# for existing readers. This marker describes the graph nesting contract.
STORY_PLAN_SCHEMA_VERSION = 2

# Brief signals → heat (adult max IRON · 2026-07-24: pin max when adult evidence)
_HEAT_MAX_MARKERS: tuple[str, ...] = (
    "成人",
    "办事",
    "性爱",
    "里番",
    "色气",
    "大尺度",
    "尺度拉满",
    "脱衣",
    "裸",
    "露点",
    "肉戏",
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
    "nude",
    "undress",
    "strip",
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


def _is_non_story_section(title: str) -> bool:
    """Whether a labelled source section is production metadata, not a scene."""
    label = re.sub(r"[【】#*\s]", "", title or "").casefold()
    return any(
        marker in label
        for marker in (
            "角色表",
            "人物表",
            "角色设定",
            "人物设定",
            "格式",
            "制作说明",
            "制作备注",
            "镜头说明",
            "字幕说明",
            "元数据",
        )
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
_EPISODE_HEADER = re.compile(
    r"(?m)^[ \t]*(?:#{1,4}[ \t]*)?(第[一二三四五六七八九十百\d]+[集章]|Episode[ \t]*\d+|EP[ \t]*\d+)[ \t]*[:：\-—]?[ \t]*([^\n]*)$",
    re.IGNORECASE,
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
    # Beat-specific tags keep multi-shot reuse of one sentence unique (timeline guard)
    nar = _clip_nar(piece, max_chars)
    need_sex = ph in {"act", "climax"}
    sex_tag_by_cb = {
        "entry": "顶入",
        "union": "跨坐",
        "rhythm": "沉腰",
        "lock": "锁腰",
        "finish": "办穿",
        "hook": "余颤",
    }
    spice_tag_by_cb = {
        "undress": "滑肩",
        "entry": "贴紧",
        "union": "咬合",
        "rhythm": "喘",
        "lock": "攥紧",
        "finish": "腿软",
        "hook": "未完",
    }
    if need_sex and not nar_has_sex_verb(nar):
        tag = sex_tag_by_cb.get(cb) or ("沉腰" if "沉腰" not in nar else "办穿")
        if len(nar) + len(tag) + 1 <= max_chars:
            nar = f"{nar.rstrip('。.!！')}。{tag}。"
        else:
            nar = _clip_nar(f"{nar}{tag}", max_chars)
    elif not nar_has_spice(nar):
        # light dual-entendre suffix that hits spice markers without erasing story
        tag = spice_tag_by_cb.get(cb) or ("色" if "色" not in nar else "喘")
        if len(nar) + len(tag) <= max_chars and tag not in nar:
            if len(tag) == 1:
                nar = _clip_nar(nar + tag, max_chars)
            else:
                nar = _clip_nar(f"{nar.rstrip('。.!！')}。{tag}", max_chars)
    return nar


def detect_heat_signals(text: str) -> dict[str, Any]:
    """Parse brief for heat_scale / hardcore.

    Adult max IRON (2026-07-24): adult markers → heat_scale=max + spice extreme intent.
    Explicit soft/medium/hot in text still wins as non-max (caller may pass genre).
    Empty brief does not silent-pin max (genre=adult default handles plan path).
    """
    raw = (text or "").strip()
    low = raw.lower()
    # Explicit cool-down wins
    if any(
        m in low or m in raw
        for m in (
            "heat_scale=soft",
            "heat_scale:soft",
            "heat_scale=medium",
            "heat_scale:medium",
            "heat soft",
            "降火",
            "不要色",
            "全年龄",
            "全年齢",
        )
    ):
        return {
            "heat_scale": "soft",
            "audience_profile": None,
            "spine": "default",
            "hardcore": False,
            "dual_climax": False,
            "evidence_max": False,
            "spice_level": None,
        }
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
        "spice_level": "extreme" if want_max else None,
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

_PLOT_POINT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "character_secret",
        ("秘密", "真相", "隐瞒", "不为人知", "身份", "过去", "背叛", "照片背面"),
    ),
    (
        "danger_omen",
        ("危险", "警告", "追杀", "威胁", "不能打开", "不要告诉", "小心", "出事", "血", "枪"),
    ),
    (
        "relationship_promise",
        ("答应", "承诺", "等我", "保护你", "不会离开", "只爱", "下次", "换你", "跟我走"),
    ),
    (
        "prop_clue",
        ("钥匙", "照片", "手机", "录音", "信", "戒指", "项链", "文件", "盒子", "门票", "名单"),
    ),
    (
        "world_info",
        ("规则", "传说", "组织", "禁令", "能力", "制度", "历史", "档案", "实验"),
    ),
)

_GENRE_POINT_QUESTION: dict[str, dict[str, str]] = {
    "mystery": {
        "character_secret": "这个秘密会被谁先发现？",
        "prop_clue": "这个线索会把调查带向哪里？",
        "danger_omen": "警告背后真正的危险是什么？",
        "relationship_promise": "这句承诺会不会成为新的破绽？",
        "world_info": "这条规则究竟隐藏了什么例外？",
    },
    "drama": {
        "character_secret": "主角会为这个秘密付出什么代价？",
        "prop_clue": "这个物件会改变谁和谁的关系？",
        "danger_omen": "他们会选择面对危险还是逃开？",
        "relationship_promise": "这句承诺能否经受下一次选择？",
        "world_info": "这条规则会限制谁的选择？",
    },
    "adult": {
        "character_secret": "这个秘密会在谁面前失守？",
        "prop_clue": "这个物件会把两人的距离推到哪一步？",
        "danger_omen": "下一步会是谁先越过边界？",
        "relationship_promise": "这句承诺会兑现还是被反过来利用？",
        "world_info": "这条规则会怎样改变下一次行动？",
    },
    "arthouse": {
        "character_secret": "这个未说出口的秘密会留下什么回声？",
        "prop_clue": "这个物件会让哪段记忆重新出现？",
        "danger_omen": "这份不安会在什么时刻显形？",
        "relationship_promise": "这句承诺会留下靠近还是离开的余韵？",
        "world_info": "这条规则会让谁失去原来的位置？",
    },
    "documentary": {
        "character_secret": "这个说法还需要什么事实来验证？",
        "prop_clue": "这份证据能支持哪一个结论？",
        "danger_omen": "这个警告对应的现实风险是什么？",
        "relationship_promise": "这项承诺是否有可核验的后果？",
        "world_info": "这条规则如何影响现实中的谁？",
    },
}


def normalize_story_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical multi-episode graph from legacy or current input."""
    if not isinstance(graph, dict):
        raise TypeError("story graph must be an object")
    out = copy.deepcopy(graph)
    episodes = out.get("episodes")
    if not isinstance(episodes, list) or not any(isinstance(ep, dict) for ep in episodes):
        scenes = out.get("scenes") if isinstance(out.get("scenes"), list) else []
        if not scenes:
            beats = out.get("beats") if isinstance(out.get("beats"), list) else []
            shots = out.get("shots") if isinstance(out.get("shots"), list) else []
            if beats:
                scenes = [{"id": "sc01", "title": "Main", "beats": beats}]
            elif shots:
                scenes = [
                    {
                        "id": "sc01",
                        "title": "Main",
                        "beats": [{"id": "bt01", "order": 1, "shots": shots}],
                    }
                ]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for scene in scenes:
            if isinstance(scene, dict):
                grouped.setdefault(
                    str(scene.get("episode_id") or out.get("episode_id") or "ep01"), []
                ).append(scene)
        episodes = [
            {
                "id": episode_id,
                "episodeNumber": index,
                "title": out.get("title") or f"Episode {index}",
                "targetDuration": out.get("targetDuration") or out.get("target_duration"),
                "openingHook": out.get("openingHook") or out.get("opening_hook"),
                "endingHook": out.get("endingHook") or out.get("ending_hook"),
                "scenes": episode_scenes,
            }
            for index, (episode_id, episode_scenes) in enumerate(grouped.items(), start=1)
        ] or [{"id": "ep01", "episodeNumber": 1, "title": "Episode 1", "scenes": []}]

    canonical_episodes: list[dict[str, Any]] = []
    for ei, raw_ep in enumerate(episodes, start=1):
        if not isinstance(raw_ep, dict):
            continue
        ep = raw_ep
        ep.setdefault("id", f"ep{ei:02d}")
        ep.setdefault("episodeNumber", ei)
        raw_scenes = ep.get("scenes") if isinstance(ep.get("scenes"), list) else []
        canonical_scenes: list[dict[str, Any]] = []
        for si, raw_scene in enumerate(raw_scenes, start=1):
            if not isinstance(raw_scene, dict):
                continue
            scene = raw_scene
            scene.setdefault("id", f"sc{si:02d}")
            raw_beats = scene.get("beats") if isinstance(scene.get("beats"), list) else None
            if raw_beats is None:
                raw_beats = [
                    {"id": f"{scene['id']}_bt01", "order": 1, "shots": scene.get("shots") or []}
                ]
            canonical_beats: list[dict[str, Any]] = []
            for bi, raw_beat in enumerate(raw_beats, start=1):
                if not isinstance(raw_beat, dict):
                    continue
                beat = raw_beat
                beat.setdefault("id", f"{scene['id']}_bt{bi:02d}")
                beat["shots"] = [
                    shot for shot in (beat.get("shots") or []) if isinstance(shot, dict)
                ]
                for shi, shot in enumerate(beat["shots"], start=1):
                    shot.setdefault("id", f"{beat['id']}_sh{shi:02d}")
                canonical_beats.append(beat)
            scene["beats"] = canonical_beats
            scene.pop("shots", None)
            canonical_scenes.append(scene)
        ep["scenes"] = canonical_scenes
        canonical_episodes.append(ep)
    out["episodes"] = canonical_episodes
    out["story_plan_schema_version"] = STORY_PLAN_SCHEMA_VERSION
    for key in ("scenes", "beats", "shots"):
        out.pop(key, None)
    return out


def export_legacy_story_plan(graph: dict[str, Any]) -> dict[str, Any]:
    """Export the canonical graph for an explicitly legacy flat consumer."""
    canonical = normalize_story_graph(graph)
    out = {k: copy.deepcopy(v) for k, v in canonical.items() if k != "episodes"}
    scenes: list[dict[str, Any]] = []
    beats: list[dict[str, Any]] = []
    shots: list[dict[str, Any]] = []
    for ep in canonical["episodes"]:
        for scene in ep.get("scenes") or []:
            scene_out = {k: copy.deepcopy(v) for k, v in scene.items() if k != "beats"}
            scene_out.update({"episode_id": ep.get("id"), "beats": []})
            for beat in scene.get("beats") or []:
                beat_out = {k: copy.deepcopy(v) for k, v in beat.items() if k != "shots"}
                beat_out.update(
                    {"episode_id": ep.get("id"), "scene_id": scene.get("id"), "shots": []}
                )
                for shot in beat.get("shots") or []:
                    shot_out = copy.deepcopy(shot)
                    shot_out.update(
                        {
                            "episode_id": ep.get("id"),
                            "scene_id": scene.get("id"),
                            "beat_id": beat.get("id"),
                        }
                    )
                    beat_out["shots"].append(shot_out)
                    shots.append(shot_out)
                scene_out["beats"].append(beat_out)
                beats.append(beat_out)
            scenes.append(scene_out)
    out.update({"scenes": scenes, "beats": beats, "shots": shots, "story_plan_schema_version": 1})
    return out


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


def _has_japanese_kana(text: object) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", str(text or "")))


def _plot_point_question(point_type: str, genre: str, excerpt: str) -> str:
    questions = _GENRE_POINT_QUESTION.get(genre) or _GENRE_POINT_QUESTION["adult"]
    return questions.get(point_type) or f"这段信息接下来会造成什么后果：{_clip_nar(excerpt, 24)}？"


def _extract_plot_point_candidates(
    raw: str,
    *,
    genre: str = "adult",
    source_refs: list[str] | None = None,
    episode_hint: int | None = None,
) -> list[dict[str, Any]]:
    """Deterministic high-signal candidate extraction; never calls a provider."""
    text = (raw or "").strip()
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])\s*|\n+", text) if part.strip()]
    refs = list(source_refs or []) or ["planner:unmapped-source"]
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, sentence in enumerate(sentences):
        matched: list[tuple[str, str]] = []
        for point_type, markers in _PLOT_POINT_MARKERS:
            hits = [marker for marker in markers if marker in sentence]
            if hits:
                matched.append((point_type, hits[0]))
        if not matched:
            continue
        # One sentence yields one point; priority follows the marker table.
        point_type, marker = matched[0]
        key = (point_type, sentence)
        if key in seen:
            continue
        seen.add(key)
        confidence = 0.92 if matched else 0.0
        source_ref = refs[min(index, len(refs) - 1)]
        candidates.append(
            {
                "candidate_id": f"candidate_{point_type}_{index + 1:03d}",
                "point_type": point_type,
                "marker": marker,
                "source_refs": [source_ref],
                "source_excerpt": _clip_nar(sentence, 160),
                "audience_question": _plot_point_question(point_type, genre, sentence),
                "visible_evidence": _clip_nar(sentence, 120),
                "confidence": confidence,
                "authoring_status": "confirmed" if confidence >= 0.85 else "candidate",
                "episode_hint": episode_hint,
                "source_index": index,
            }
        )
    # Keep the authoring surface bounded: a paragraph may contain many
    # keywords, but only the first three source-grounded promises enter the
    # automatic episode plan. The remaining ambiguity stays out of the lock.
    return candidates[:3]


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
            # A heading is production metadata, not a playable scene. Do not
            # turn it into VO/shot material merely to keep the plan non-empty.
            if body and not _is_non_story_section(title):
                chunks.append({"title": title or f"Scene {i + 1}", "body": body})
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
            # Never manufacture a scene from a timing/format/character heading.
            # A heading alone has neither observable action nor narration.
            if not body or _is_non_story_section(title):
                continue
            chunks.append({"title": title, "body": body})
        if chunks:
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


def _episode_chunks(raw: str, *, source_refs: list[str] | None = None) -> list[dict[str, Any]]:
    """Prefer explicit episode/chapter headers; otherwise keep one episode."""
    text = (raw or "").strip()
    matches = list(_EPISODE_HEADER.finditer(text))
    if len(matches) < 2:
        return [{"title": "Episode 1", "body": text, "source_refs": list(source_refs or [])}]
    chunks: list[dict[str, Any]] = []
    refs = list(source_refs or [])
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title_suffix = match.group(1).strip()
        body = text[start:end].strip()
        if not body:
            continue
        ref = refs[min(i, len(refs) - 1)] if refs else f"source:episode_{i + 1:02d}"
        chunks.append(
            {"title": title_suffix or f"Episode {i + 1}", "body": body, "source_refs": [ref]}
        )
    return chunks or [{"title": "Episode 1", "body": text, "source_refs": list(source_refs or [])}]


def normalize_story(
    raw: str,
    *,
    title_hint: str | None = None,
    source_path: str | None = None,
    source_evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """story.normalize — structured story package (no LLM)."""
    raw = (raw or "").strip()
    title = _extract_title(raw, title_hint)
    chars = _character_candidates(raw)
    locs = _location_candidates(raw)
    dialogues = _dialogue_blocks(raw)
    chunks = _scene_chunks(raw)
    episode_chunks = _episode_chunks(raw, source_refs=source_evidence_refs)
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
        warnings.append(
            "no quoted dialogue detected — default dialogue_drama with pure-visual "
            "coverage and/or candidate character lines (not third-person storyteller VO)"
        )

    heat = detect_heat_signals(raw)
    genre_info = detect_genre(raw, heat=heat)
    genre = genre_info["genre"]
    # genre=adult pins max + extreme unless brief explicitly soft/medium (P0 · 2026-07-29)
    scale_now = str(heat.get("heat_scale") or "").strip().lower()
    if genre == "adult" and scale_now not in {"soft", "medium"}:
        if scale_now != "max":
            spine = str(heat.get("spine") or "default")
            if spine in {"", "default"}:
                spine = "adult_max"
            heat = {
                **heat,
                "heat_scale": "max",
                "spice_level": heat.get("spice_level") or "extreme",
                "spine": spine,
                "evidence_max": True,
                "pinned_by": "genre_adult_default",
            }
        elif not heat.get("spice_level"):
            heat = {**heat, "spice_level": "extreme"}
        warnings.append(
            f"adult genre pin → spine={heat.get('spine')} heat_scale={heat.get('heat_scale')} "
            f"spice={heat.get('spice_level')}"
        )
    elif heat.get("evidence_max"):
        warnings.append(
            f"adult heat signals → spine={heat.get('spine')} heat_scale={heat.get('heat_scale')}"
        )
    for gw in genre_info.get("warnings", []):
        warnings.append(gw)
    plot_point_candidates = _extract_plot_point_candidates(
        raw,
        genre=genre,
        source_refs=source_evidence_refs,
    )

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
        "episode_chunks": episode_chunks,
        "source_evidence_refs": list(source_evidence_refs or []),
        "plot_point_candidates": plot_point_candidates,
        # Cinema dialogue is the product default (Chinese spoken primary).
        "vo_mode_suggest": "dialogue_drama",
        "heat_signals": heat,
        "genre_evidence": genre_info["evidence"],
        "warnings": warnings,
        "source_map": {
            "method": "deterministic_v1",
            "note": "Agent may refine; this is structure-only normalize",
        },
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
        "vo_mode": normalized.get("vo_mode_suggest") or "dialogue_drama",
    }


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
    char_ids = [c["id"] for c in (normalized.get("character_candidates") or []) if c.get("id")]
    if not char_ids:
        char_ids = ["hero"]

    shot_i = 1
    episode_outs: list[dict[str, Any]] = []
    episode_chunks = normalized.get("episode_chunks") or [
        {"title": "Episode 1", "body": normalized.get("raw_excerpt") or "", "source_refs": []}
    ]
    for episode_number, ep_chunk in enumerate(episode_chunks, start=1):
        if not isinstance(ep_chunk, dict):
            continue
        ep_norm = dict(normalized)
        ep_norm.update(
            {
                "title": str(ep_chunk.get("title") or f"Episode {episode_number}"),
                "logline": _clip_nar(
                    str(ep_chunk.get("body") or normalized.get("logline") or ""), 80
                ),
                "raw_excerpt": str(ep_chunk.get("body") or normalized.get("raw_excerpt") or "")[
                    :2000
                ],
                "scene_chunks": _scene_chunks(str(ep_chunk.get("body") or "")),
                "plot_point_candidates": _extract_plot_point_candidates(
                    str(ep_chunk.get("body") or ""),
                    genre=str(normalized.get("genre") or "adult"),
                    source_refs=list(
                        ep_chunk.get("source_refs") or normalized.get("source_evidence_refs") or []
                    ),
                    episode_hint=episode_number,
                ),
            }
        )
        episode = structure_episode(
            ep_norm, target_duration=target_duration, episode_number=episode_number
        )
        scenes = segment_scenes(ep_norm, episode)
        total = float(episode["targetDuration"])
        weights = [max(1, len(str(sc.get("body") or ""))) for sc in scenes]
        wsum = sum(weights) or 1
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
                    episode_number=episode_number,
                )
                shot_i += len(shots)
                beats_out.append(
                    {
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
                )
            scenes_out.append(
                {
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
            )
        episode_outs.append(
            {
                **episode,
                "scenes": scenes_out,
                "status": "planning",
                "plot_point_candidates": list(ep_norm.get("plot_point_candidates") or []),
            }
        )

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
        "episodes": episode_outs
        or [structure_episode(normalized, target_duration=target_duration)],
        "story": _draft_story_contract(normalized),
        "characters": characters,
        "locations": locations,
        "props": [],
        "warnings": list(normalized.get("warnings") or []),
    }
    screenplay = (
        normalized.get("dialogue_screenplay")
        if isinstance(normalized.get("dialogue_screenplay"), dict)
        else None
    )
    if isinstance(screenplay, dict):
        graph["dialogue_screenplay"] = copy.deepcopy(screenplay)
        graph["dialogue_mode"] = str(screenplay.get("mode") or "")
    # Preserve the source dialogue as first-class, editable story truth.  The
    # planned shots are only an initial coverage scaffold; the line id binds
    # later TTS, state-photo, lipsync, subtitle and review evidence.
    dialogue_blocks: list[dict[str, Any]] = []
    if isinstance(screenplay, dict) and screenplay.get("mode") == "dialogue_drama":
        for scene in screenplay.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("scene_id") or "")
            for turn in scene.get("dialogue_turns") or []:
                if not isinstance(turn, dict):
                    continue
                dialogue_blocks.append(
                    {
                        "id": turn.get("line_id"),
                        "speaker": turn.get("speaker"),
                        "addressee": turn.get("addressee"),
                        "text": turn.get("dialogue_zh") or turn.get("subtitle_zh"),
                        "caption_text": turn.get("subtitle_zh"),
                        "spoken_ja": turn.get("dialogue_ja"),
                        "translation_status": turn.get("translation_status"),
                        "emotion": turn.get("emotion"),
                        "subtext": turn.get("subtext"),
                        "actions": copy.deepcopy(turn.get("actions") or {}),
                        "screen_mode": str(turn.get("screen_mode") or "on_camera"),
                        "lipsync_required": bool(turn.get("lipsync_required", True)),
                        "scene_state_id": str(turn.get("scene_state_id") or ""),
                        "gaze": turn.get("gaze"),
                        "props": list(turn.get("props") or []),
                        "state_delta": turn.get("state_delta"),
                        "source_refs": list(
                            (turn.get("source_evidence") or {}).get("source_refs") or []
                        ),
                        "source_excerpt": (turn.get("source_evidence") or {}).get("source_excerpt"),
                        "provenance": turn.get("provenance")
                        or (turn.get("source_evidence") or {}).get("provenance"),
                        "review_status": turn.get("review_status"),
                        "scene_id": scene_id,
                        "coverage_intent": copy.deepcopy(scene.get("coverage_intent") or {}),
                    }
                )
    if not dialogue_blocks:
        dialogue_blocks = [
            row for row in (normalized.get("dialogue_blocks") or []) if isinstance(row, dict)
        ]
    if dialogue_blocks:
        cast_by_name = {
            str(char.get("name") or char.get("identity") or "").strip(): str(char.get("id") or "")
            for char in characters
            if isinstance(char, dict)
        }
        planned_shots = [
            (beat, shot)
            for episode in graph["episodes"]
            if isinstance(episode, dict)
            for scene in (episode.get("scenes") or [])
            if isinstance(scene, dict)
            for beat in (scene.get("beats") or [])
            if isinstance(beat, dict)
            for shot in (beat.get("shots") or [])
            if isinstance(shot, dict)
        ]
        ledger: list[dict[str, Any]] = []
        for index, row in enumerate(dialogue_blocks):
            if index >= len(planned_shots) and planned_shots:
                # Do not collapse later dialogue lines onto the same visual
                # shot: each line must retain a distinct production identity.
                parent, source = planned_shots[-1]
                target = copy.deepcopy(source)
                target["id"] = f"{source['id']}_dlg{index + 1:02d}"
                target["filmSpecShotId"] = target["id"]
                target["order"] = int(source.get("order") or index) + 1
                target["dialogueLineIds"] = []
                parent.setdefault("shots", []).append(target)
                planned_shots.append((parent, target))
            target = planned_shots[index][1] if index < len(planned_shots) else {}
            source_speaker = str(row.get("speaker") or "").strip()
            speaker = cast_by_name.get(source_speaker) or _slug(source_speaker, char_ids[0])
            line_id = str(row.get("id") or f"dlg_{index + 1:02d}")
            entry = {
                "line_id": line_id,
                "speaker": speaker,
                "text": str(row.get("text") or "").strip(),
                "caption_text": str(row.get("caption_text") or row.get("text") or "").strip(),
                "spoken_ja": str(row.get("spoken_ja") or "").strip()
                or (
                    str(row.get("text") or "").strip()
                    if _has_japanese_kana(row.get("text"))
                    else ""
                ),
                "translation_status": str(
                    row.get("translation_status")
                    or ("ready" if _has_japanese_kana(row.get("text")) else "pending")
                ),
                "emotion": str(row.get("emotion") or ""),
                "subtext": str(row.get("subtext") or ""),
                "addressee": str(row.get("addressee") or ""),
                "actions": copy.deepcopy(row.get("actions") or {}),
                "screen_mode": str(row.get("screen_mode") or "on_camera"),
                "lipsync_required": bool(row.get("lipsync_required", True)),
                "scene_state_id": str(row.get("scene_state_id") or ""),
                "gaze": str(row.get("gaze") or ""),
                "props": list(row.get("props") or []),
                "state_delta": str(row.get("state_delta") or ""),
                "source_refs": list(row.get("source_refs") or []),
                "source_excerpt": str(row.get("source_excerpt") or ""),
                "provenance": str(row.get("provenance") or ""),
                "review_status": str(row.get("review_status") or ""),
                "scene_ref": str(row.get("scene_id") or ""),
                "coverage_intent": copy.deepcopy(row.get("coverage_intent") or {}),
                "beat_ref": str(target.get("beatId") or ""),
                "shot_ref": str(target.get("id") or ""),
                "delivery_note": "",
                "lipsync_anchor": True,
                "is_key_line": index == 0,
            }
            ledger.append(entry)
            if target:
                target["dialogueLineIds"] = [line_id]
        graph["dialogue_ledger"] = ledger
    if isinstance(normalized.get("reception"), dict):
        graph["story_reception"] = copy.deepcopy(normalized["reception"])
    _seed_narrative_contract(graph, normalized)
    _autofill_dialogue_narrative_contract(graph)
    ensure_graph_controls(graph)
    graph["content_sha256"] = graph_content_sha256(graph)
    return graph


def _autofill_dialogue_narrative_contract(graph: dict[str, Any]) -> None:
    """Bind source dialogue to performance fields without inventing plot facts."""
    ledger = [row for row in (graph.get("dialogue_ledger") or []) if isinstance(row, dict)]
    if not ledger:
        return
    by_id = {str(row.get("line_id") or ""): row for row in ledger}
    for episode in graph.get("episodes") or []:
        if not isinstance(episode, dict):
            continue
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for beat in scene.get("beats") or []:
                if not isinstance(beat, dict):
                    continue
                board = (
                    beat.get("director_board")
                    if isinstance(beat.get("director_board"), dict)
                    else {}
                )
                if board.get("approval_state") == "approved":
                    board["approval_state"] = "review"
                beat["director_board"] = board
                for shot in beat.get("shots") or []:
                    if not isinstance(shot, dict):
                        continue
                    line_ids = [
                        str(item)
                        for item in (shot.get("dialogueLineIds") or [])
                        if str(item).strip()
                    ]
                    line = by_id.get(line_ids[0]) if line_ids else None
                    if not isinstance(line, dict):
                        continue
                    text = str(line.get("text") or "").strip()
                    if text and shot.get("playable_action") in (
                        None,
                        "",
                        AUTHORING_PLACEHOLDER,
                    ):
                        shot["playable_action"] = f"角色表演并说出来源台词：{text}"
                    for target, source in (
                        ("subtext", "subtext"),
                        ("gaze_target", "addressee"),
                        ("reaction_trigger", "state_delta"),
                    ):
                        value = str(line.get(source) or "").strip()
                        if value and shot.get(target) in (
                            None,
                            "",
                            AUTHORING_PLACEHOLDER,
                        ):
                            shot[target] = value


def _seed_narrative_contract(graph: dict[str, Any], normalized: dict[str, Any]) -> None:
    """Turn semantic source candidates into shot-bound narrative contracts."""
    episodes = [ep for ep in graph.get("episodes") or [] if isinstance(ep, dict)]
    points: list[dict[str, Any]] = []
    authoring_queue: list[dict[str, Any]] = []
    source_refs = list(normalized.get("source_evidence_refs") or [])
    if not source_refs:
        source_refs = [str(normalized.get("source_path") or "planner:story-source")]

    def flatten(ep: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        beats: list[dict[str, Any]] = []
        shots: list[dict[str, Any]] = []
        for scene in ep.get("scenes") or []:
            for beat in scene.get("beats") or []:
                if isinstance(beat, dict):
                    beats.append(beat)
                    shots.extend(sh for sh in beat.get("shots") or [] if isinstance(sh, dict))
        return beats, shots

    for index, ep in enumerate(episodes):
        ep_id = str(ep.get("id") or f"ep{index + 1:02d}")
        beats, shots = flatten(ep)
        if not beats or not shots:
            continue
        first_beat = beats[0]
        first_shot = shots[0]
        last_beat = beats[-1]
        last_shot = shots[-1]
        candidates = [c for c in (ep.get("plot_point_candidates") or []) if isinstance(c, dict)]
        confirmed = [c for c in candidates if c.get("authoring_status") == "confirmed"][:3]
        authoring_queue.extend(c for c in candidates if c not in confirmed)
        if not confirmed:
            fallback = {
                "candidate_id": f"{ep_id}_candidate_01",
                "point_type": "custom",
                "source_refs": list(source_refs),
                "source_excerpt": str(ep.get("logline") or normalized.get("raw_excerpt") or ""),
                "audience_question": "本集真正留下的未解决问题是什么？",
                "visible_evidence": "needs_authoring",
                "confidence": 0.0,
                "authoring_status": "candidate",
                "episode_hint": index + 1,
            }
            authoring_queue.append(fallback)
            confirmed = [fallback]
        next_ep = episodes[index + 1].get("id") if index + 1 < len(episodes) else None
        point_ids: list[str] = []
        for point_index, candidate in enumerate(confirmed[:3], start=1):
            beat = beats[min(point_index, len(beats) - 1)]
            beat_shots = [sh for sh in beat.get("shots") or [] if isinstance(sh, dict)] or [
                first_shot
            ]
            point_id = f"{ep_id}_point_{point_index:02d}"
            point_ids.append(point_id)
            payoff_episode = (
                int(str(next_ep).removeprefix("ep"))
                if next_ep
                else int(str(ep_id).removeprefix("ep"))
            )
            point = {
                "point_id": point_id,
                "point_type": candidate.get("point_type") or "custom",
                "source_refs": list(candidate.get("source_refs") or source_refs),
                "source_excerpt": candidate.get("source_excerpt") or "",
                "introduced_episode": ep_id,
                "introduced_beat_id": str(beat.get("id") or ""),
                "introduced_shot_ids": [str(sh.get("id")) for sh in beat_shots if sh.get("id")],
                "visible_evidence": candidate.get("visible_evidence")
                or str(beat.get("action") or ""),
                "audience_question": candidate.get("audience_question")
                or "这个线索接下来会带来什么变化？",
                "planned_payoff_episode": payoff_episode,
                "payoff_condition": "下一集必须回应该线索并改变人物或局势"
                if next_ep
                else "本季结束时明确回收或声明下一季承诺",
                "status": "planted" if next_ep else "season_hook",
                "confidence": float(candidate.get("confidence") or 0.0),
                "authoring_status": candidate.get("authoring_status") or "confirmed",
            }
            points.append(point)
            for shot in beat_shots:
                shot.setdefault("narrative_point_ids", []).append(point_id)
        if not point_ids:
            point_ids = [f"{ep_id}_point_01"]
        opening_point = points[-len(point_ids)]
        ending_point = points[-1]
        ep["opening_hook"] = {
            "hook_id": f"{ep_id}_opening",
            "point_id": opening_point["point_id"],
            "beat_id": str(first_beat.get("id") or ""),
            "shot_ids": [str(first_shot.get("id") or "")],
            "source_refs": list(opening_point["source_refs"]),
            "question": str(opening_point["audience_question"]),
            "visible_evidence": opening_point["visible_evidence"],
        }
        ep["mid_episode_points"] = point_ids
        ep["ending_hook"] = {
            "hook_id": f"{ep_id}_ending",
            "point_id": ending_point["point_id"],
            "beat_id": str(last_beat.get("id") or ""),
            "shot_ids": [str(last_shot.get("id") or "")],
            "source_refs": list(ending_point["source_refs"]),
            "question": str(ending_point["audience_question"]),
            "visible_evidence": ending_point["visible_evidence"],
        }
        ep["carry_in_points"] = []
        ep["payoff_points"] = []
        ep["new_audience_question"] = ending_point["audience_question"]
        ep["endingHook"] = ep["ending_hook"]["question"]
        reversal_beat = beats[len(beats) // 2]
        reversal_shot = next(
            (shot for shot in reversal_beat.get("shots") or [] if isinstance(shot, dict)),
            first_shot,
        )
        ep["narrative_arc"] = {
            "opening_hook_id": ep["opening_hook"]["hook_id"],
            "escalation_beat_id": str(beats[min(1, len(beats) - 1)].get("id") or ""),
            "reversal": {
                "beat_id": str(reversal_beat.get("id") or ""),
                "shot_ids": [str(reversal_shot.get("id") or "")],
                "setup_expectation": "needs_authoring",
                "revealed_truth": "needs_authoring",
                "visible_consequence": "needs_authoring",
                "source_refs": list(source_refs),
            },
            "payoff": {
                "beat_id": str(last_beat.get("id") or ""),
                "shot_ids": [str(last_shot.get("id") or "")],
                "resolves_point_ids": [],
                "visible_change": "needs_authoring",
            },
            "ending_mode": "closed" if index == len(episodes) - 1 else "next_episode",
        }
        if index > 0:
            previous_ep = episodes[index - 1]
            previous_ids = list(previous_ep.get("mid_episode_points") or [])
            ep["carry_in_points"] = previous_ids
            ep["payoff_points"] = previous_ids
            for previous_point in points:
                if previous_point.get("point_id") in previous_ids:
                    previous_point["status"] = "paid_off"
                    previous_point["payoff_evidence"] = {
                        "episode": ep_id,
                        "beat_id": str(first_beat.get("id") or ""),
                        "shot_ids": [str(first_shot.get("id") or "")],
                        "visible_change": str(
                            first_shot.get("visible_change")
                            or first_shot.get("must_show")
                            or "回应上一集钩子"
                        ),
                    }
            ep["narrative_arc"]["payoff"]["resolves_point_ids"] = previous_ids

    graph["plot_points"] = points
    graph["plot_point_candidates"] = authoring_queue
    if episodes:
        final_beats, final_shots = flatten(episodes[-1])
        final_beat = (
            final_beats[-2] if len(final_beats) > 1 else (final_beats[-1] if final_beats else {})
        )
        resolution_shots = [
            shot for shot in final_beat.get("shots") or [] if isinstance(shot, dict)
        ]
        final_shot = (
            resolution_shots[-1] if resolution_shots else (final_shots[-1] if final_shots else {})
        )
        graph["story_resolution"] = {
            "episode_id": str(episodes[-1].get("id") or ""),
            "beat_id": str(final_beat.get("id") or ""),
            "shot_ids": [str(final_shot.get("id") or "")],
            "climax_choice": "needs_authoring",
            "outcome": "needs_authoring",
            "final_state": "needs_authoring",
        }
    graph["narrative_policy"] = {
        "midpoint_min": 1,
        "payoff_window_episodes": 3,
        "require_plan_evidence": True,
        "require_executed_evidence": True,
        "require_reversal": True,
        "require_complete_resolution": True,
        "season_end_mode": "season_hook"
        if episodes and any(p.get("status") == "season_hook" for p in points)
        else "closed",
    }


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
    # Bind the projection to the exact persisted graph.  Normalization below
    # is a read-time compatibility transform and can otherwise change the
    # hash, leaving every freshly projected locked graph falsely stale.
    source_revision = int(graph.get("revision") or 1)
    source_sha256 = graph_content_sha256(graph)
    graph = normalize_story_graph(graph)
    base = dict(base_spec or {})
    ep = (graph.get("episodes") or [{}])[0]
    if not isinstance(ep, dict):
        ep = {}
    title = str(
        graph.get("project", {}).get("title") or ep.get("title") or base.get("title") or "untitled"
    )
    logline = str(ep.get("openingHook") or (normalized or {}).get("logline") or title)
    vo_mode = str(
        (normalized or {}).get("vo_mode_suggest") or base.get("vo_mode") or "dialogue_drama"
    )
    if vo_mode not in {"storyteller", "character", "hybrid", "dialogue_drama"}:
        vo_mode = "dialogue_drama"

    cast_ids = [
        c.get("id") for c in (graph.get("characters") or []) if isinstance(c, dict) and c.get("id")
    ]
    if not cast_ids:
        cast_ids = ["hero"]

    dialogue_by_shot = {
        str(line.get("shot_ref") or ""): line
        for line in (graph.get("dialogue_ledger") or [])
        if isinstance(line, dict) and str(line.get("shot_ref") or "").strip()
    }
    scenes_fs: list[dict[str, Any]] = []
    previous_broll_kind: str | None = None
    for ep_item in graph.get("episodes") or []:
        if not isinstance(ep_item, dict):
            continue
        for sc in ep_item.get("scenes") or []:
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
                        "scene_id": sc.get("id") or sc.get("sceneId"),
                        "title": film.get("title") or sh.get("narrativePurpose") or sh.get("id"),
                        "shot_role": film.get("shot_role") or "hero",
                        "dramatic_function": film.get("dramatic_function")
                        or sh.get("dramaticFunction")
                        or "action",
                        "duration_sec": float(
                            film.get("duration_sec") or sh.get("targetDuration") or 5
                        ),
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
                    dialogue_line = dialogue_by_shot.get(str(shot_obj["id"]))
                    if vo_mode == "dialogue_drama" and dialogue_line:
                        from performance_state import performance_state_id

                        camera = dsl.setdefault("camera", {})
                        if isinstance(camera, dict):
                            screen_mode = str(dialogue_line.get("screen_mode") or "on_camera")
                            near_sizes = {
                                "close-up",
                                "ecu",
                                "extreme close-up",
                                "medium close-up",
                            }
                            if (
                                screen_mode == "on_camera"
                                and str(camera.get("shot_size") or "").strip().lower()
                                not in near_sizes
                            ):
                                camera["shot_size"] = "medium close-up"

                        actions = (
                            dialogue_line.get("actions")
                            if isinstance(dialogue_line.get("actions"), dict)
                            else {}
                        )
                        gaze = dialogue_line.get("gaze")
                        gaze_target = (
                            str(gaze.get("target") or "")
                            if isinstance(gaze, dict)
                            else str(gaze or "")
                        )
                        gaze_target = (
                            gaze_target
                            or str(dialogue_line.get("addressee") or "")
                            or str(sh.get("gaze_target") or "")
                            or "listener"
                        )
                        props = list(dialogue_line.get("props") or sh.get("props") or [])
                        caption_text = str(
                            dialogue_line.get("caption_text")
                            or dialogue_line.get("dialogue_zh")
                            or dialogue_line.get("subtitle_zh")
                            or dialogue_line.get("text")
                            or ""
                        ).strip()
                        spoken_ja = str(
                            dialogue_line.get("spoken_ja") or dialogue_line.get("dialogue_ja") or ""
                        ).strip()
                        spoken_zh = str(
                            dialogue_line.get("spoken_zh")
                            or dialogue_line.get("dialogue_zh")
                            or dialogue_line.get("text")
                            or caption_text
                            or ""
                        ).strip()
                        dlang = "zh"
                        text = spoken_zh or caption_text or spoken_ja
                        if spoken_zh or (
                            caption_text and re.search(r"[\u4e00-\u9fff]", caption_text)
                        ):
                            translation_status = "ready"
                        elif spoken_ja:
                            dlang = "ja"
                            text = spoken_ja
                            translation_status = (
                                dialogue_line.get("translation_status") or "pending"
                            )
                        else:
                            translation_status = (
                                dialogue_line.get("translation_status") or "pending"
                            )
                        caption_text = caption_text or spoken_zh or text
                        duration = max(
                            float(shot_obj["duration_sec"]),
                            round(max(1.0, len(text) / 4.0) + 0.8, 1),
                        )
                        shot_obj.update(
                            {
                                "duration_sec": duration,
                                "dialogue_line_id": dialogue_line["line_id"],
                                "speaker": dialogue_line["speaker"],
                                "addressee": dialogue_line.get("addressee"),
                                # dialogue_drama: Chinese spoken primary; nar empty.
                                "dialogue": text,
                                "caption_text": caption_text,
                                "dialogue_ja": spoken_ja,
                                "translation_status": translation_status,
                                "performance_state": {
                                    "emotion": dialogue_line.get("emotion") or "neutral",
                                    "subtext": dialogue_line.get("subtext") or "",
                                    "gaze_target": gaze_target,
                                    "head_angle": sh.get("head_angle")
                                    or "camera-safe three-quarter",
                                    "body_orientation": sh.get("body_orientation")
                                    or "oriented toward addressee",
                                    "gesture": actions.get("during")
                                    or sh.get("playable_action")
                                    or "",
                                    "props": props,
                                    "lighting": dsl.get("lighting") or "",
                                    "space_position": sh.get("space_position")
                                    or dsl.get("space_position")
                                    or "",
                                    "continuity_parent": sh.get("continuity_parent") or "",
                                },
                                "performance_intent": {
                                    "emotion": dialogue_line.get("emotion") or "neutral",
                                    "subtext": dialogue_line.get("subtext") or "",
                                    "actions": actions,
                                    "gaze_target": gaze_target,
                                    "state_delta": dialogue_line.get("state_delta") or {},
                                },
                                "screen_mode": str(dialogue_line.get("screen_mode") or "on_camera"),
                                "speaker_on_camera": str(
                                    dialogue_line.get("screen_mode") or "on_camera"
                                )
                                == "on_camera",
                                "lipsync": str(dialogue_line.get("screen_mode") or "on_camera")
                                == "on_camera"
                                and bool(dialogue_line.get("lipsync_required", True)),
                                "lipsync_required": str(
                                    dialogue_line.get("screen_mode") or "on_camera"
                                )
                                == "on_camera"
                                and bool(dialogue_line.get("lipsync_required", True)),
                                "dialogue_motion_route": "auto",
                                "audio_cues": [
                                    {
                                        "kind": "voice",
                                        "line_type": "dialogue",
                                        "speaker": dialogue_line["speaker"],
                                        "spoken_text": text,
                                        "caption_text": caption_text,
                                        "language": dlang,
                                        "translation_status": translation_status,
                                        "emotion": dialogue_line.get("emotion") or "",
                                        "purpose": "dialogue",
                                        "lipsync_required": True,
                                        "start_offset_sec": 0.0,
                                        "duration_sec": duration,
                                    }
                                ],
                                "content_channels": {
                                    "voice": {
                                        "kind": "dialogue",
                                        "text": text,
                                        "on_camera": True,
                                        "lipsync": True,
                                    },
                                    "performance": {
                                        "playable_action": actions.get("during")
                                        or sh.get("playable_action")
                                        or "",
                                        "gaze_target": gaze_target,
                                        "pre_line_action": actions.get("before") or "",
                                        "post_line_action": actions.get("after") or "",
                                    },
                                    "motion": {
                                        "action": dsl.get("action") or "",
                                        "camera_motion": dsl.get("motion") or "",
                                        "scene_trigger": "dialogue_turn",
                                    },
                                },
                            }
                        )
                        shot_obj["performance_state_id"] = str(
                            dialogue_line.get("scene_state_id") or ""
                        ) or performance_state_id(shot_obj)
                        shot_obj["dialogue_broll"] = default_dialogue_broll(
                            shot_obj, previous_kind=previous_broll_kind
                        )
                        if shot_obj["dialogue_broll"]:
                            previous_broll_kind = str(shot_obj["dialogue_broll"][0]["kind"])
                    elif vo_mode == "dialogue_drama":
                        # Coverage remains visual/silent unless an editor adds
                        # a justified narration cue later.  Silence makes the
                        # absence of TTS deliberate and auditable.
                        camera = dsl.setdefault("camera", {})
                        if isinstance(camera, dict) and not any(
                            prior.get("screen_mode") == "action_cover" for prior in shots_fs
                        ):
                            camera["shot_size"] = "wide"
                        shot_obj.update(
                            {
                                "screen_mode": "action_cover",
                                "audio_cues": [
                                    {
                                        "kind": "silence",
                                        "start_offset_sec": 0.0,
                                        "duration_sec": float(shot_obj["duration_sec"]),
                                    }
                                ],
                            }
                        )
                    else:
                        shot_obj["nar"] = film.get("nar") or sh.get("nar") or "……"
                    hp = film.get("heat_phase") or sh.get("heatPhase")
                    if hp:
                        shot_obj["heat_phase"] = hp
                    cb = film.get("coitus_beat") or sh.get("coitusBeat")
                    if cb:
                        shot_obj["coitus_beat"] = cb
                    sab = film.get("sex_arc_beat") or sh.get("sexArcBeat")
                    if sab:
                        shot_obj["sex_arc_beat"] = sab
                        if not dsl.get("sex_arc_beat"):
                            dsl["sex_arc_beat"] = sab
                    sp = film.get("sex_pose") or sh.get("sexPose")
                    if sp:
                        shot_obj["sex_pose"] = sp
                        if not dsl.get("sex_pose"):
                            dsl["sex_pose"] = sp
                    ws = film.get("wardrobe_state") or sh.get("wardrobeState")
                    if ws:
                        shot_obj["wardrobe_state"] = ws
                        if not dsl.get("wardrobe_state"):
                            dsl["wardrobe_state"] = ws
                    if isinstance(sh.get("creative"), dict):
                        shot_obj["creative"] = copy.deepcopy(sh["creative"])
                    shots_fs.append(shot_obj)
            scenes_fs.append(
                {
                    "id": sc.get("id"),
                    "episode_id": ep_item.get("id"),
                    "title": sc.get("title") or "Scene",
                    "summary": sc.get("synopsis") or "",
                    "shots": shots_fs,
                }
            )

    if vo_mode == "dialogue_drama":
        dialogue_shots = [
            shot
            for scene in scenes_fs
            for shot in (scene.get("shots") or [])
            if isinstance(shot, dict) and shot.get("screen_mode") == "on_camera"
        ]
        coverage_beats = {
            str(shot.get("beat_id") or "")
            for scene in scenes_fs
            for shot in (scene.get("shots") or [])
            if isinstance(shot, dict)
            and shot.get("screen_mode") in {"reaction", "action_cover", "silence"}
        }
        # A beat may carry several short speech lines, but it must end on a
        # listener/action/silence image. Grouping by beat avoids one video per
        # line while making the edit rhythm explicit and auditable.
        final_speaker_by_beat: dict[str, dict[str, Any]] = {}
        for shot in dialogue_shots:
            beat = str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "")
            if beat:
                final_speaker_by_beat[beat] = shot
        insert_after: dict[str, list[dict[str, Any]]] = {}
        ordered_dialogue = [
            shot
            for scene in scenes_fs
            for shot in (scene.get("shots") or [])
            if isinstance(shot, dict) and shot.get("screen_mode") == "on_camera"
        ]
        prev_speaker_global = ""
        reverse_beats: set[str] = set()
        for shot in ordered_dialogue:
            sp = str(shot.get("speaker") or "")
            beat = str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "")
            if prev_speaker_global and sp and sp != prev_speaker_global and beat:
                reverse_beats.add(beat)
            if sp:
                prev_speaker_global = sp
        for beat, source in final_speaker_by_beat.items():
            if beat in coverage_beats:
                continue
            source_dsl = source.get("dsl") if isinstance(source.get("dsl"), dict) else {}
            has_action = bool(
                str(source.get("playable_action") or source.get("must_show") or "").strip()
            )
            use_reverse = beat in reverse_beats or bool(str(source.get("addressee") or "").strip())
            mode = "action_cover" if has_action and not use_reverse else "reaction"
            addressee = str(source.get("addressee") or "listener")
            speaker = str(source.get("speaker") or "")
            headroom = (
                "vertical 9:16 face-priority, full head and both shoulders inside frame, "
                "ample headroom, safe framing no cropping, eyes readable"
            )
            if use_reverse:
                title = "正反打·听者反应（OTS reverse）"
                action = (
                    f"listener {addressee} absorbs {speaker}'s line; "
                    "shot-reverse-shot opposite eyeline, over-shoulder reverse angle"
                )
                motion = "subtle reverse-angle hold, eye reaction, micro head turn toward speaker"
                camera = {
                    "shot_size": "medium close-up",
                    "angle": "eye level",
                    "axis": "reverse",
                    "framing": f"over-shoulder reverse, {headroom}",
                }
                coverage_role = "reverse_reaction"
            elif mode == "action_cover":
                title = "对白节拍后的动作承接"
                action = "show the prop/action consequence of the completed line"
                motion = "hold, subtle action and eye movement"
                camera = {"shot_size": "medium close-up", "framing": headroom}
                coverage_role = mode
            else:
                title = "对白节拍后的听者反应"
                action = "listener absorbs the line; a visible emotional reaction"
                motion = "hold, subtle action and eye movement"
                camera = {"shot_size": "medium close-up", "framing": headroom}
                coverage_role = mode
            reaction = {
                "id": f"{source['id']}_{coverage_role}",
                "scene_id": source.get("scene_id"),
                "title": title,
                "shot_role": "hero",
                "dramatic_function": "action" if mode == "action_cover" else "reaction",
                "duration_sec": 1.5,
                "beat_id": beat,
                "coverage_role": coverage_role,
                "screen_mode": mode,
                "speaker_on_camera": False,
                "lipsync": False,
                "auto_dialogue_coverage": True,
                "shot_reverse_shot": use_reverse,
                "audio_cues": [{"kind": "silence", "start_offset_sec": 0.0, "duration_sec": 1.5}],
                "dsl": {
                    **source_dsl,
                    "action": action,
                    "motion": motion,
                    "camera": camera,
                    "composition": headroom,
                    "cast": (
                        [addressee]
                        if addressee and addressee not in {"listener", "pending_addressee"}
                        else source_dsl.get("cast")
                    ),
                },
            }
            insert_after.setdefault(str(source.get("id") or ""), []).append(reaction)
        for scene in scenes_fs:
            ordered: list[dict[str, Any]] = []
            for shot in scene.get("shots") or []:
                if not isinstance(shot, dict):
                    continue
                ordered.append(shot)
                ordered.extend(insert_after.get(str(shot.get("id") or ""), []))
            scene["shots"] = ordered

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
    # Optional character/story fields are validated when present. Do not emit
    # empty draft placeholders into the executable projection.
    for field in (
        "protagonist_goal",
        "protagonist_want",
        "protagonist_need",
        "protagonist_arc",
        "opposition",
        "stakes",
        "climax_choice",
        "ending_hook",
    ):
        if not str(di.get(field) or "").strip():
            di.pop(field, None)
    # A draft scaffold has blank act fields. Keep it in drama-graph authoring
    # state, but never project it as an executable film-spec contract.
    draft_act = story.get("act_structure")
    if (
        isinstance(draft_act, dict)
        and not di.get("act_structure")
        and all(
            str(draft_act.get(key) or "").strip()
            for key in ("setup", "confrontation", "resolution")
        )
    ):
        di["act_structure"] = draft_act
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

    production_mode = str(
        (graph.get("project") or {}).get("production_mode")
        or (normalized or {}).get("production_mode")
        or base.get("production_mode")
        or "shortform"
    )
    genre_default = "drama" if production_mode == "longform" else "adult"
    spec: dict[str, Any] = {
        **base,
        "title": title,
        "description": logline,
        "aspect_ratio": "9:16",
        "production_mode": production_mode,
        "genre": story.get("genre") or (normalized or {}).get("genre") or genre_default,
        "vo_mode": vo_mode,
        "dialogue_spoken_lang": (
            "zh" if vo_mode == "dialogue_drama" else base.get("dialogue_spoken_lang", "zh")
        ),
        "narration_spoken_lang": "zh"
        if vo_mode == "dialogue_drama"
        else base.get("narration_spoken_lang", "zh"),
        "caption_lang": base.get("caption_lang") or "zh",
        "audio_cues_strict": vo_mode == "dialogue_drama",
        "tts_rehearsal_required": vo_mode == "dialogue_drama",
        "dialogue_state_strict": vo_mode == "dialogue_drama",
        "dialogue_benchmark_required": vo_mode == "dialogue_drama",
        "narration_gap_strict": vo_mode == "dialogue_drama",
        "audio_policy": (
            {"mode": "auto", "allow_lipsync": True}
            if vo_mode == "dialogue_drama"
            else base.get("audio_policy")
        ),
        "narration_budget_strict": vo_mode == "dialogue_drama",
        "content_channels_strict": vo_mode == "dialogue_drama",
        "sex_vo_auto_apply": (
            False
            if vo_mode == "dialogue_drama" and base.get("sex_vo_auto_apply") is None
            else base.get("sex_vo_auto_apply")
        ),
        "tts_backend": (
            "edge" if vo_mode == "dialogue_drama" else base.get("tts_backend") or "mimo"
        ),
        "i2v_provider": base.get("i2v_provider") or "grok",
        "caption_mode": base.get("caption_mode") or "zh",
        "director_intent": di,
        "scenes": scenes_fs,
        "episodes": [
            {
                "id": ep.get("id"),
                "episodeNumber": ep.get("episodeNumber"),
                "title": ep.get("title"),
                "opening_hook": ep.get("opening_hook"),
                "mid_episode_points": ep.get("mid_episode_points") or [],
                "ending_hook": ep.get("ending_hook"),
                "carry_in_points": ep.get("carry_in_points") or [],
                "payoff_points": ep.get("payoff_points") or [],
                "new_audience_question": ep.get("new_audience_question") or "",
            }
            for ep in graph.get("episodes") or []
            if isinstance(ep, dict)
        ],
        "plot_points": [
            dict(point) for point in graph.get("plot_points") or [] if isinstance(point, dict)
        ],
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
            "source_revision": source_revision,
            "source_sha256": source_sha256,
            "generated_at": utc_now(),
            "state": graph.get("state") or "draft",
        },
    }
    if production_mode == "longform":
        target_duration = sum(
            float(item.get("targetDuration") or 0)
            for item in graph.get("episodes") or []
            if isinstance(item, dict)
        )
        spec["longform_profile"] = {
            "target_duration_sec": target_duration,
            "act_count": 3,
            "unit_max_duration_sec": 90,
            "approval_policy": "three_gates",
        }
        spec["director_intent"]["audience"] = base_di.get("audience") or "8–15 分钟竖屏剧情片观众"
    # Keep user source on film-spec for fidelity gate + agent rewrites
    raw_ex = str((normalized or {}).get("raw_excerpt") or "").strip()
    if raw_ex:
        spec["source_excerpt"] = raw_ex[:4000]
        spec["user_source_fidelity_strict"] = True
    # genre=adult without heat: still pin max (escape only soft/medium)
    genre_proj = str(spec.get("genre") or "adult")
    if (
        not heat.get("heat_scale")
        and genre_proj == "adult"
        and str(heat.get("heat_scale") or "") not in {"soft", "medium"}
    ):
        heat = {
            **heat,
            "heat_scale": "max",
            "spice_level": "extreme",
            "spine": heat.get("spine") or "adult_max",
            "evidence_max": True,
            "pinned_by": "project_adult_default",
        }
    if heat.get("heat_scale"):
        spec["heat_scale"] = heat["heat_scale"]
        spec["heat_phase_auto"] = True
        spec["sex_floor_strict"] = True
        spec["sex_wardrobe_strict"] = True
        spec["sex_vo_strict"] = True
        spec["heat_arc_strict"] = True
        if heat.get("heat_scale") == "max":
            spec["challenge_max_scale"] = True  # 持续挑战尺度最大
            spec["erotic_impact_strict"] = True
            spec["sex_arc_strict"] = True
            spec["sex_detail_cu_strict"] = True
            spec["both_undress_strict"] = True
        # max IRON: spice always extreme when max
        spec["spice_level"] = heat.get("spice_level") or (
            "extreme" if heat.get("heat_scale") == "max" or heat.get("hardcore") else "explicit"
        )
        if heat.get("hardcore"):
            spec["sex_min_duration_ratio"] = 0.55
            spec["coitus_strict"] = True
            spec["size_ladder_strict"] = True
            spec["montage_strict"] = True
            spec["pose_strict"] = True
            spec["sex_vo_motion_strict"] = True
            spec["audience_profile"] = "hardcore_male"
        else:
            # max adult IRON: sex floor 50% (overrideable)
            if spec.get("sex_min_duration_ratio") is None:
                spec["sex_min_duration_ratio"] = 0.50
        if coitus_beats:
            spec["coitus_grammar"] = {
                "enabled": True,
                "mute_frame_test": True,
                "beats": coitus_beats,
            }
    spec["narrative_policy"] = dict(graph.get("narrative_policy") or {})
    if isinstance(graph.get("story_reception"), dict):
        spec["story_reception"] = copy.deepcopy(graph["story_reception"])
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
                "schema_version": 2,
                "provider_default": "grok-imagine",
                "title": title,
                "theme": theme,
                "aspect_ratio": "9:16",
                "width": 720,
                "height": 1280,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "review_contract_version": 2,
                "truth_contract": {
                    "source_of_truth": "local-contract-and-receipts",
                    "contract_sha256": "",
                },
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


def _apply_plan_feedback(normalized: dict[str, Any], root: Path) -> None:
    """Apply execution feedback from previous runs to inform this planning run.

    Reads narrative-evidence.json if it exists and uses duration deviations
    to adjust beat weight suggestions. The adjustments are stored in
    normalized["plan_feedback"] for downstream consumers to inspect.
    """
    try:
        from plan_feedback import plan_adjustments_for_next_run

        feedback = plan_adjustments_for_next_run(root=str(root))
        if feedback.get("status") == "adjustments_available":
            normalized["plan_feedback"] = feedback
    except Exception:  # noqa: BLE001
        pass


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
    character_id_overrides: dict[str, str] | None = None,
    source_evidence_refs: list[str] | None = None,
    reception: dict[str, Any] | None = None,
    story_mode: str = "narrative",
    production_mode: str = "shortform",
) -> dict[str, Any]:
    """End-to-end Phase 3 planner for a film root."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    production_mode = str(production_mode or "shortform")
    if production_mode not in {"shortform", "longform"}:
        raise ValueError("production_mode must be shortform|longform")
    if production_mode == "longform":
        if not 480 <= float(target_duration) <= 900:
            raise ValueError("longform target duration must be within 480..900 seconds")
        if apply_film_spec:
            raise ValueError(
                "longform plan run is draft-only; lock the graph then run plan project"
            )

    normalized = normalize_story(
        raw,
        title_hint=title,
        source_path=source_path,
        source_evidence_refs=source_evidence_refs,
    )
    normalized["story_mode"] = str(story_mode or "narrative")
    normalized["production_mode"] = production_mode
    if reception:
        from story_reception import reception_summary, story_contract_seed

        source = reception["source"]
        treatment = reception["treatment"]
        normalized["raw_excerpt"] = str(source["raw_text"])[:2000]
        normalized["source_chars"] = len(str(source["raw_text"]))
        normalized["source_path"] = str(source_path or source["source_ref"])
        normalized["source_evidence_refs"] = [str(source["source_ref"])]
        normalized["title"] = str(treatment.get("title") or normalized["title"])
        normalized["logline"] = str(treatment.get("logline") or normalized["logline"])
        normalized["story_contract_seed"] = story_contract_seed(reception)
        normalized["received_episode_contract"] = treatment.get("episode_contract")
        normalized["reception"] = reception_summary(
            reception, path=Path(source_path) if source_path else None
        )
        normalized["source_map"] = {
            **dict(normalized.get("source_map") or {}),
            "method": "agent_t2t_story_reception_v1",
            "original_source_sha256": source["sha256"],
            "planning_text_sha256": hashlib.sha256(
                str(treatment["planning_text"]).encode("utf-8")
            ).hexdigest(),
        }
    from dialogue_screenplay import (
        build_dialogue_screenplay,
        validate_dialogue_screenplay,
    )

    received_screenplay = (
        reception.get("dialogue_screenplay")
        if isinstance(reception, dict) and isinstance(reception.get("dialogue_screenplay"), dict)
        else None
    )
    screenplay = (
        copy.deepcopy(received_screenplay)
        if isinstance(received_screenplay, dict)
        else build_dialogue_screenplay(normalized, reception=reception)
    )
    screenplay_validation = validate_dialogue_screenplay(
        screenplay,
        strict=isinstance(received_screenplay, dict),
    )
    if isinstance(received_screenplay, dict) and not screenplay_validation["ok"]:
        codes = ",".join(
            str(issue.get("code") or "SCREENPLAY_INVALID")
            for issue in screenplay_validation.get("issues") or []
        )
        raise ValueError(f"received dialogue_screenplay is not lock-ready: {codes}")
    normalized["dialogue_screenplay"] = screenplay
    normalized["dialogue_screenplay_validation"] = screenplay_validation
    sp_mode = str(screenplay.get("mode") or "dialogue_drama")
    if sp_mode == "storyteller":
        normalized["vo_mode_suggest"] = "storyteller"
    elif sp_mode == "monologue":
        normalized["vo_mode_suggest"] = "character"
    else:
        normalized["vo_mode_suggest"] = "dialogue_drama"
    if character_id_overrides:
        for candidate in normalized.get("character_candidates") or []:
            name = str(candidate.get("name") or "")
            override = character_id_overrides.get(name)
            if override:
                candidate["id"] = override
                candidate["source"] = "intake"

    # Apply execution feedback from previous runs (if any evidence exists)
    _apply_plan_feedback(normalized, root)

    _ensure_film_root_skeleton(
        root,
        title=str(normalized.get("title") or "untitled"),
        theme=str(normalized.get("logline") or "")[:200],
    )
    if production_mode == "longform":
        from production_book import init_production_book

        init_production_book(
            root,
            title=str(normalized.get("title") or "untitled"),
            rigor="professional",
            format_pack="vertical-longform",
            genre_pack=str(normalized.get("genre") or "drama"),
            quality_target="premium_vertical",
        )
    write_json(root / "receipts" / "story-normalize.json", normalized)

    previous_graph = read_json(root / "drama-graph.json") or None
    graph = build_planned_graph(normalized, target_duration=target_duration, root=root)
    graph.setdefault("project", {})["production_mode"] = production_mode
    graph = stabilize_shot_ids(graph, previous_graph)
    if root:
        graph["project"]["root"] = str(root)

    # Pre-plan structural check — verify the graph has the essential
    # top-level keys that make it usable downstream.  Draft-level
    # missing fields (obstacle, tactic, …) are expected and handled
    # by the narrative lock flow later.
    REQUIRED_GRAPH_KEYS = ("story", "episodes", "story_resolution")
    missing_keys = [k for k in REQUIRED_GRAPH_KEYS if k not in graph]
    if missing_keys:
        raise FilmError(
            f"PRE_PLAN_NARRATIVE: graph missing required keys: {','.join(missing_keys)}"
        )

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
            received_contract = normalized.get("received_episode_contract")
            if isinstance(received_contract, dict) and isinstance(spec.get("serial"), dict):
                if spec["serial"].get("enabled") is True:
                    spec["episode_contract"] = copy.deepcopy(received_contract)
            write_json(root / "film-spec.json", spec)
            # The screenplay is human-authored; this package is its stable
            # production projection.  It deliberately stays pending until
            # real TTS/lipsync evidence is recorded.
            from dialogue_scene_package import build_dialogue_scene_package

            write_json(
                root / "dialogue-scene-package.json",
                build_dialogue_scene_package(graph, spec),
            )
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
                "dialogue_scene_package": str(root / "dialogue-scene-package.json"),
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
