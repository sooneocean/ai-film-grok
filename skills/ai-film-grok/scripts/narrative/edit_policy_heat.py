#!/usr/bin/env python3
"""Heat arc / wardrobe / sex / VO spice policies.

Extracted from edit_policy.py (C4 · 2026-08-04) so the core stretch/transition
surface stays smaller. Public symbols re-exported by edit_policy for back-compat.
"""

from __future__ import annotations

import re
from typing import Any

# Prefer in-package sibling when edit_policy is mid-import (shim-safe cycle).
import sys as _sys

_ep = _sys.modules.get("narrative.edit_policy")
if _ep is not None and getattr(_ep, "PolicyError", None) is not None:
    _COITUS_PSEUDO_ONLY = _ep._COITUS_PSEUDO_ONLY
    _COITUS_READABLE_MARKERS = _ep._COITUS_READABLE_MARKERS
    COITUS_BEATS = _ep.COITUS_BEATS
    COITUS_REQUIRED_BEATS = _ep.COITUS_REQUIRED_BEATS
    PolicyError = _ep.PolicyError
else:
    from edit_policy import (  # type: ignore
        _COITUS_PSEUDO_ONLY,
        _COITUS_READABLE_MARKERS,
        COITUS_BEATS,
        COITUS_REQUIRED_BEATS,
        PolicyError,
    )

# --- Heat arc / multi-heroine (adult max iron · 2026-07-24) ---
# Adult max IRON: meat-ratio high, heat max, undress/expose when possible.
# Sex duration + intimacy + setup + bare peak are hard on heat_scale=max
# (write-spec via sex_floor_strict / sex_wardrobe_strict / heat_arc_strict).

HEAT_SCALES = frozenset({"soft", "medium", "hot", "max"})
HEAT_PHASES = frozenset({"setup", "foreplay", "act", "climax", "afterglow", "bridge"})
INTIMACY_PHASES = frozenset({"foreplay", "act", "climax"})
# Sex / intercourse beats only (NOT foreplay) — user KPI: 「性爱片段」
SEX_PHASES = frozenset({"act", "climax"})
# Adult max IRON targets (2026-07-24 · raised: 30%→50%, intimacy 60%→70%)
ADVISORY_MAX_INTIMACY_RATIO = 0.70
ADVISORY_MAX_SETUP_RATIO = 0.20
ADVISORY_MAX_SEX_DURATION_RATIO = 0.55  # advise target for max
# Hard floors on max: intimacy 60% (achievable on 8-shot spines); advise still 70%
EXTREME_INTIMACY_FLOOR = 0.60
EXTREME_SETUP_CEILING = 0.20
# Product floor: act+climax duration share of total plate (duration_sec weighted)
# heat_scale=max → default hard at write-spec (sex_floor_strict default True)
DEFAULT_SEX_DURATION_FLOOR = 0.50
# hot soft floor (warning only)
HOT_SEX_DURATION_FLOOR = 0.15
# hardcore_male / 尺度太小 target
HARDCORE_SEX_DURATION_TARGET = 0.55
# max films must reach bare peak at least once
DEFAULT_BARE_PEAK_REQUIRED = True
# Continuous challenge max scale (2026-07-24+): heat phase rank must not regress
# before climax; max 2 consecutive plateau shots at same phase rank pre-climax
HEAT_PHASE_ESCALATION_RANK: dict[str, int] = {
    "setup": 0,
    "bridge": 0,
    "foreplay": 1,
    "act": 2,
    "climax": 3,
    "afterglow": 4,
}
MAX_PRE_CLIMAX_PLATEAU_SHOTS = 2  # same rank in a row before climax → stall
DEFAULT_SHOT_DURATION_SEC = 6.0

# spice_level: how dirty VO must be (v1.10)
SPICE_LEVELS = frozenset({"suggestive", "explicit", "extreme"})
# extreme requires denser sex verbs / body nouns — dual-entendre alone is too mild
_NAR_EXTREME_MARKERS: tuple[str, ...] = (
    "沉腰",
    "顶弄",
    "顶撞",
    "再顶",
    "吃进",
    "办穿",
    "办完",
    "跨坐",
    "骑",
    "插",
    "入",
    "泄",
    "射",
    "高潮",
    "穴",
    "肏",
    "操",
    "干穿",
    "吞",
    "更深",
    "锁腰",
    "腿软",
    "失声",
    "磨",
    "thrust",
    "grind",
    "mount",
    "straddle",
    "climax",
    "hips-sink",
    "整根",
    "内射",
    "中出",
    "灌满",
    "喷",
    "creampie",
    "internal ejaculation",
    "internal peak",
    "overflow",
    "bottoming out",
    "deep thrust",
    "penetrating",
    "biological",
    "溢出",
    "体内",
    "残留",
    "泄爆",
)
# dual-entendre only — counts as spice but TOO_MILD under extreme
_NAR_MILD_ONLY_MARKERS: tuple[str, ...] = (
    "加演",
    "加练",
    "补课",
    "作业",
    "练习",
    "规矩",
    "认输",
    "落锁",
    "门闩",
    "下一场",
    "未完",
    "诚实",
    "夜色",
    "灯",
)

# sex_pose catalog (suggestive names · multi-pose variety)
SEX_POSES = frozenset(
    {
        "straddle",
        "cowgirl",
        "reverse_cowgirl",
        "missionary_pin",
        "from_behind",
        "standing_lift",
        "lotus",
        "edge_oral",
        "lap_grind",
        "wall_pin",
        "prone_bone",
        "side_entry",
    }
)
COITUS_BEAT_DEFAULT_POSE: dict[str, str] = {
    "entry": "wall_pin",
    "undress": "lap_grind",
    "union": "straddle",
    "rhythm": "cowgirl",
    "lock": "lotus",
    "finish": "missionary_pin",
    "hook": "side_entry",
}

# hardcore montage craft spine (n-1 joins)
HARDCORE_CRAFT_SPINE: tuple[str, ...] = (
    "whip_soft",
    "insert_cut",
    "cut_on_action",
    "smash_cut",
    "montage_jump",
    "montage_jump",
    "insert_cut",
    "cut_on_action",
    "smash_cut",
    "mood_hold",
)

# Wardrobe ladder for sex (办事必须卸甲/脱衣 · 2026-07-21)
# full/armored = 登场定妆；partial = 失序半脱；undressed/bare = 办事层裸露可读
# Rank is undress progress only — must be monotonic non-decreasing (衣服不回穿)
WARDROBE_STATES = frozenset({"full", "armored", "partial", "undressed", "bare"})
WARDROBE_UNDRESS_RANK: dict[str, int] = {
    "full": 0,
    "armored": 1,
    "partial": 2,
    "undressed": 3,
    "bare": 4,
}
SEX_WARDROBE_OK = frozenset({"partial", "undressed", "bare"})
SEX_WARDROBE_STRONG = frozenset({"undressed", "bare"})  # max IRON: act+ uses these
# Phase → minimum wardrobe rank floor when auto-escalating (能脱就脱 / 能露就露)
PHASE_WARDROBE_FLOOR: dict[str, str] = {
    "foreplay": "partial",
    "act": "undressed",
    "climax": "bare",
    # afterglow: no floor — inherit peak via clamp only (never re-dress)
}
_EXPOSED_WARDROBE_MARKERS: tuple[str, ...] = (
    "undressed",
    "unclothed",
    "nude",
    "naked",
    "bare skin",
    "bare chest",
    "bare breasts",
    "bare shoulders",
    "bare thighs",
    "bare midriff",
    "stripped",
    "lingerie only",
    "only lingerie",
    "armor off",
    "armor removed",
    "armor discarded",
    "dress off",
    "dress removed",
    "dress discarded",
    "clothes off",
    "clothing removed",
    "half-naked",
    "half naked",
    "topless",
    "skin-to-skin",
    "skin to skin",
    "wardrobe disorder",
    "hiked hem",
    "skirt hiked",
    "open bodice",
    "open shirt",
    "disheveled clothes",
    "clothes in disorder",
    "裸",
    "半裸",
    "全裸",
    "裸露",
    "脱衣",
    "卸甲",
    "铠甲卸",
    "铠甲落",
    "衣落",
    "裙掀",
    "掀裙",
    "肩带崩",
    "失序到办事",
    "办事层",
)
_UNDRESS_ACTION_MARKERS: tuple[str, ...] = (
    "undress",
    "undresses",
    "undressing",
    "strips",
    "stripping",
    "strip off",
    "removes armor",
    "remove armor",
    "armor falls",
    "peels off",
    "slides dress",
    "dress slides",
    "pulls dress",
    "unbuckles",
    "unhooks",
    "unzips",
    "unbuttons",
    "shrugs off",
    "takes off",
    "taking off",
    "脱下",
    "脱掉",
    "卸下",
    "卸甲",
    "解扣",
    "解带",
    "拉下拉链",
    "褪去",
    "扯开",
    "扯落",
    "滑落肩",
    "肩带滑",
)
_FULL_DRESS_MARKERS: tuple[str, ...] = (
    "full armor",
    "complete armor",
    "armor intact",
    "fully armored",
    "fully clothed",
    "full dress intact",
    "intact outfit",
    "formal attire",
    "neat dress",
    "pristine outfit",
    "全装",
    "铠甲完整",
    "正装完好",
    "衣着整齐",
    "一丝不苟",
)

# VO 荤梗 / 办事动词（实打实成人办事剧 · 2026-07-21）
# heat_scale=max：每镜 nar 至少命中 1 个 荤梗；act/climax 必须命中办事动词
_NAR_SPICE_MARKERS: tuple[str, ...] = (
    # 身体 / 办事
    "沉腰",
    "顶弄",
    "顶撞",
    "再顶",
    "磨",
    "骑",
    "跨坐",
    "办穿",
    "办完",
    "办事",
    "加办",
    "吃进",
    "吞",
    "更深",
    "腿软",
    "锁腰",
    "锁腿",
    "攥",
    "喘",
    "湿",
    "潮",
    "硬",
    "软了",
    "腰线",
    "胯",
    "臀",
    "胸",
    "乳",
    "穴",
    "插",
    "入",
    "泄",
    "射",
    "高潮",
    "失声",
    "余颤",
    "余韵",
    "贴身",
    "贴耳",
    "耳语",
    "压进",
    "按进",
    "拽进",
    "咬",
    "舔",
    "吻",
    "蹭",
    "夹",
    "绞",
    "灌",
    "弄",
    "肏",
    "操",
    "干穿",
    "干",
    "上床",
    "脱",
    "卸甲",
    "半裸",
    "裸",
    "失序",
    "肩带",
    "裙",
    "扣",
    # 荤梗 / 双关（可当 setup/afterglow 入口，act 仍要办事动词）
    "加演",
    "加练",
    "补课",
    "作业",
    "练习",
    "规矩",
    "认输",
    "落锁",
    "门闩",
    "换你顶",
    "下一场",
    "未完",
    "诚实",
    "入口",
    "结合",
    "节奏",
    "hips",
    "grind",
    "thrust",
    "mount",
    "climax",
    "moan",
    "wet",
    "bare",
    "straddle",
    "sink",
)
_NAR_SEX_VERB_MARKERS: tuple[str, ...] = (
    "沉腰",
    "顶弄",
    "顶撞",
    "再顶",
    "磨",
    "骑",
    "跨坐",
    "办穿",
    "办完",
    "办事",
    "吃进",
    "更深",
    "腿软",
    "锁腰",
    "锁腿",
    "高潮",
    "失声",
    "余颤",
    "插",
    "入",
    "泄",
    "射",
    "肏",
    "操",
    "干穿",
    "干",
    "结合",
    "节奏",
    "换你顶",
    "grind",
    "thrust",
    "mount",
    "climax",
    "straddle",
    "hips",
    "sink",
)
# 纯文艺 / 扫兴（单独出现且无荤梗时 fail）
_NAR_LITERARY_ONLY_HINTS: tuple[str, ...] = (
    "灯灭了",
    "故事却",
    "话说",
    "月光",
    "夜色温柔",
    "沉默",
    "心跳加速",
    "脸红",
    "不好意思",
    "下课了",
    "今天主题",
)

# dramatic_function → default heat_phase when author omits heat_phase
_DRAMATIC_TO_HEAT_PHASE: dict[str, str] = {
    "hook": "setup",
    "approach": "setup",
    "bridge": "bridge",
    "sensory": "foreplay",
    "reaction": "foreplay",
    "action": "act",
    "afterglow": "afterglow",
}


def normalize_heat_scale(value: object | None, *, default: str | None = None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    s = str(value).strip().lower()
    if s not in HEAT_SCALES:
        raise PolicyError(f"heat_scale must be one of {sorted(HEAT_SCALES)}; got {value!r}")
    return s


def normalize_heat_phase(value: object | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    s = str(value).strip().lower()
    if s not in HEAT_PHASES:
        raise PolicyError(f"heat_phase must be one of {sorted(HEAT_PHASES)}; got {value!r}")
    return s


def infer_heat_phase(shot: dict[str, Any]) -> str:
    """Infer heat_phase from explicit field or dramatic_function."""
    explicit = normalize_heat_phase(shot.get("heat_phase"))
    if explicit:
        return explicit
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    explicit = normalize_heat_phase(dsl.get("heat_phase"))
    if explicit:
        return explicit
    df = str(shot.get("dramatic_function") or "").strip().lower()
    # max-scale action near end often climax: leave to author; default act
    return _DRAMATIC_TO_HEAT_PHASE.get(df, "bridge")


def apply_heat_phase_defaults(shots: list[dict[str, Any]]) -> list[str]:
    """Optionally fill missing heat_phase from dramatic_function only (no climax guessing)."""
    filled: list[str] = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        if normalize_heat_phase(shot.get("heat_phase")):
            continue
        phase = infer_heat_phase(shot)
        shot["heat_phase"] = phase
        filled.append(str(shot.get("id") or f"idx{i}"))
    return filled


def heat_phase_escalation_rank(phase: str | None) -> int:
    """Higher = hotter. afterglow only valid after climax peak."""
    if not phase:
        return 0
    return HEAT_PHASE_ESCALATION_RANK.get(str(phase).strip().lower(), 0)


def lint_heat_escalation_challenge(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Force continuous challenge of maximum heat on max films.

    Product rule (2026-07-24 user): 持续挑战尺度最大.
    - Phase rank must not drop before climax (泄火 = fail)
    - After first act, cannot return to setup for body-avoidance
    - Pre-climax: cannot plateau same rank for > MAX_PRE_CLIMAX_PLATEAU_SHOTS
      without advancing (stall = fail)
    - Afterglow only after climax peak was reached
    """
    scale = (heat_scale or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"}:
        return {
            "ok": True,
            "codes": [],
            "warning_count": 0,
            "info_count": 0,
            "issues": [],
            "heat_scale": scale,
            "note": "escalation challenge skipped (not max/hot)",
        }

    peak_rank = -1
    peak_sid: str | None = None
    climax_seen = False
    plateau_run = 0
    last_rank: int | None = None
    regression_ids: list[str] = []
    stall_ids: list[str] = []
    afterglow_early: list[str] = []
    post_act_setup: list[str] = []
    act_seen = False
    per_shot: list[dict[str, Any]] = []

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "?")
        ph = infer_heat_phase(shot)
        rank = heat_phase_escalation_rank(ph)
        row: dict[str, Any] = {"id": sid, "heat_phase": ph, "rank": rank}

        if ph == "climax":
            climax_seen = True
        if ph == "act":
            act_seen = True

        # afterglow before any climax = premature cool-down
        if ph == "afterglow" and not climax_seen:
            afterglow_early.append(sid)
            row["early_afterglow"] = True

        # phase regression before climax (泄火)
        if not climax_seen and peak_rank >= 0 and rank < peak_rank:
            # allow bridge as connective tissue only if rank gap is small and not from act
            if not (ph == "bridge" and peak_rank <= 1):
                regression_ids.append(f"{sid}:{ph}<peak@{peak_sid or '?'}")
                row["regression"] = True

        # after act has started, setup = body avoidance (泄火铺垫)
        if act_seen and not climax_seen and ph == "setup":
            post_act_setup.append(sid)
            row["post_act_setup"] = True

        # plateau: only pre-act ranks (setup/foreplay) — act may run long for meat %
        # stall = stuck in foreplay/setup without ascending to act/climax
        if not climax_seen and 0 < rank < 2:  # foreplay only
            if last_rank is not None and rank == last_rank:
                plateau_run += 1
            else:
                plateau_run = 1
            if plateau_run > MAX_PRE_CLIMAX_PLATEAU_SHOTS:
                stall_ids.append(sid)
                row["stall"] = True
        elif not climax_seen and rank == 0 and last_rank == 0:
            # long pure setup also stalls challenge
            plateau_run = (plateau_run + 1) if last_rank == 0 else 1
            # setup may open film: allow more (3) before stall
            if plateau_run > MAX_PRE_CLIMAX_PLATEAU_SHOTS + 1:
                stall_ids.append(sid)
                row["stall"] = True
        else:
            if rank >= 2:
                plateau_run = 0
            elif last_rank != rank:
                plateau_run = 1

        if rank > peak_rank:
            peak_rank = rank
            peak_sid = sid
        last_rank = rank
        per_shot.append(row)

    if regression_ids:
        _issue(
            "HEAT_ESCALATION_REGRESSION",
            "warning",
            "max IRON continuous challenge: heat_phase regressed before climax (泄火) — "
            f"{', '.join(regression_ids[:8])}. "
            "Phase must only rise setup→foreplay→act→climax until peak. "
            "禁止中途回到更冷的 phase。",
        )
    if post_act_setup:
        _issue(
            "HEAT_ESCALATION_REGRESSION",
            "warning",
            "max IRON: setup after act started (回避身体) — "
            f"{', '.join(post_act_setup[:8])}. 进入 act 后禁止再写 setup 泄火。",
        )
    if afterglow_early:
        _issue(
            "HEAT_ESCALATION_REGRESSION",
            "warning",
            "max IRON: afterglow before climax — "
            f"{', '.join(afterglow_early[:8])}. 高潮前禁止 afterglow 收火。",
        )
    if stall_ids:
        _issue(
            "HEAT_ESCALATION_STALL",
            "warning",
            "max IRON continuous challenge: pre-climax phase plateau too long — "
            f"{', '.join(stall_ids[:8])}. "
            f"同一 heat 档位连续 >{MAX_PRE_CLIMAX_PLATEAU_SHOTS} 镜必须加压升档 "
            "(foreplay→act 或 act→climax / 换体位加深)。持续挑战尺度最大。",
        )
    # No climax on max with enough shots = never reached maximum challenge
    n = sum(1 for s in shots if isinstance(s, dict))
    if scale == "max" and n >= 6 and not climax_seen and act_seen:
        _issue(
            "HEAT_ESCALATION_NO_PEAK",
            "warning",
            "max IRON: act without climax — 持续挑战必须抵达 climax bare 峰值，禁止只办事不办穿。",
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "warning_count": warn_n,
        "info_count": 0,
        "issues": issues,
        "heat_scale": scale,
        "peak_rank": peak_rank,
        "climax_seen": climax_seen,
        "regression_shots": regression_ids,
        "stall_shots": stall_ids,
        "per_shot": per_shot,
        "note": (
            "Continuous challenge max scale: phase monotonic rise to climax; "
            "no mid-film cool-down; no long plateau. See adult-max-iron."
        ),
    }


def _shot_duration_sec(shot: dict[str, Any]) -> float:
    """Plate seconds for duration-weighted heat ratios (defaults 6s)."""
    try:
        d = float(shot.get("duration_sec") or DEFAULT_SHOT_DURATION_SEC)
    except (TypeError, ValueError):
        d = DEFAULT_SHOT_DURATION_SEC
    if d < 0:
        return 0.0
    return d


def _shot_visual_blob(shot: dict[str, Any]) -> str:
    """Concatenate wardrobe-relevant text from shot + dsl for marker scan."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    parts: list[str] = []
    for key in (
        "wardrobe_state",
        "wardrobe",
        "nar",
        "title",
        "subject",
        "action",
        "start_pose",
        "end_pose",
        "motion",
        "story_beat",
        "visible_change",
        "environment",
    ):
        if key in shot and shot.get(key) is not None:
            parts.append(str(shot.get(key)))
        if key in dsl and dsl.get(key) is not None:
            parts.append(str(dsl.get(key)))
    # nested wardrobe object
    for container in (shot, dsl):
        w = container.get("wardrobe") if isinstance(container, dict) else None
        if isinstance(w, dict):
            parts.extend(str(v) for v in w.values() if v is not None)
        elif isinstance(w, str):
            parts.append(w)
    return " ".join(parts).lower()


def normalize_wardrobe_state(value: object | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    s = str(value).strip().lower().replace("-", "_")
    aliases = {
        "full_dress": "full",
        "clothed": "full",
        "dressed": "full",
        "armor": "armored",
        "armour": "armored",
        "half": "partial",
        "disorder": "partial",
        "disheveled": "partial",
        "半脱": "partial",
        "失序": "partial",
        "nude": "bare",
        "naked": "bare",
        "exposed": "bare",
        "裸": "bare",
        "半裸": "undressed",
        "脱衣": "undressed",
        "卸甲": "undressed",
    }
    s = aliases.get(s, s)
    if s not in WARDROBE_STATES:
        raise PolicyError(f"wardrobe_state must be one of {sorted(WARDROBE_STATES)}; got {value!r}")
    return s


def resolve_wardrobe_state(shot: dict[str, Any]) -> str | None:
    """Explicit wardrobe_state / dsl.wardrobe_state, else infer from visual blob."""
    if not isinstance(shot, dict):
        return None
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    for raw in (
        shot.get("wardrobe_state"),
        dsl.get("wardrobe_state"),
        (shot.get("wardrobe") or {}).get("state")
        if isinstance(shot.get("wardrobe"), dict)
        else None,
        (dsl.get("wardrobe") or {}).get("state") if isinstance(dsl.get("wardrobe"), dict) else None,
    ):
        try:
            st = normalize_wardrobe_state(raw)
        except PolicyError:
            st = None
        if st:
            return st
    blob = _shot_visual_blob(shot)
    if not blob.strip():
        return None
    # Strong exposed first
    if any(m in blob for m in ("nude", "naked", "全裸", "bare breasts", "bare chest")):
        return "bare"
    if any(m in blob for m in _EXPOSED_WARDROBE_MARKERS):
        if any(m in blob for m in ("armor", "铠甲", "dress", "裙", "strap")) and any(
            m in blob for m in _UNDRESS_ACTION_MARKERS
        ):
            return "undressed"
        if any(
            m in blob
            for m in (
                "undressed",
                "unclothed",
                "stripped",
                "armor off",
                "dress off",
                "clothes off",
                "半裸",
                "裸露",
                "卸甲",
            )
        ):
            return "undressed"
        return "partial"
    if any(m in blob for m in _FULL_DRESS_MARKERS):
        if "armor" in blob or "铠甲" in blob:
            return "armored"
        return "full"
    if "armor" in blob or "铠甲" in blob:
        return "armored"
    return None


def shot_has_undress_action(shot: dict[str, Any]) -> bool:
    blob = _shot_visual_blob(shot)
    return any(m in blob for m in _UNDRESS_ACTION_MARKERS)


def wardrobe_undress_rank(state: str | None) -> int | None:
    """Higher = more undressed. None if unknown."""
    if not state:
        return None
    return WARDROBE_UNDRESS_RANK.get(str(state).strip().lower())


def _write_shot_wardrobe_state(shot: dict[str, Any], state: str) -> None:
    """Persist wardrobe_state on shot + dsl (continuity carry / clamp write-back)."""
    shot["wardrobe_state"] = state
    dsl = shot.get("dsl")
    if not isinstance(dsl, dict):
        dsl = {}
        shot["dsl"] = dsl
    dsl["wardrobe_state"] = state


# start_pose / subject must open at prior undress level (agent + write-spec)
_WARDROBE_START_POSE_HINT: dict[str, str] = {
    "full": "fully clothed as prior beat",
    "armored": "armor still on as prior beat",
    "partial": "already half-undressed from prior beat (shirt open / straps down); do NOT start fully clothed",
    "undressed": "already undressed from prior beat (main outfit off); do NOT start fully clothed or re-armored",
    "bare": "already bare/exposed from prior beat; do NOT re-dress or put clothes back on",
}

_WARDROBE_SUBJECT_MUST_INCLUDE: dict[str, tuple[str, ...]] = {
    "partial": ("partial", "open shirt", "半脱", "失序", "yanked open", "shirt open", "straps"),
    "undressed": ("undressed", "bare skin", "半裸", "stripped", "clothes off", "outfit off"),
    "bare": ("bare", "nude", "裸", "bare skin", "exposed", "undressed"),
}


def apply_wardrobe_continuity(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    clamp_re_dress: bool | None = None,
    auto_escalate: bool | None = None,
) -> dict[str, Any]:
    """Carry wardrobe_state forward; never re-dress; escalate undress on max/hot.

    Product rule (2026-07-21+ / **IRON 2026-07-24**): 卸装阶梯 · 不回穿 · **能脱就脱/能露就露**.
    - Missing state inherits previous known (peak) state
    - Undress action on still-dressed shot bumps to at least ``partial``
    - max/hot **phase floor**: foreplay≥partial, act≥undressed, climax≥bare
    - Explicit regression: **clamp** to peak on max/hot
    - Also writes ``dsl.start_pose`` wardrobe continuity hint when missing/weak
    """
    scale = (heat_scale or "").strip().lower() or None
    if clamp_re_dress is None:
        # Default ON for adult max/hot so mechanism always fires in write-spec
        clamp_re_dress = scale in {"max", "hot"}
    if auto_escalate is None:
        auto_escalate = scale in {"max", "hot"}
    prev_state: str | None = None
    peak_state: str | None = None
    filled: list[str] = []
    bumped: list[str] = []
    clamped: list[str] = []
    escalated: list[dict[str, str]] = []
    start_pose_filled: list[str] = []

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "?")
        ph = infer_heat_phase(shot)
        st = resolve_wardrobe_state(shot)
        undress = shot_has_undress_action(shot)
        from_state = st or ""

        if st is None and prev_state is not None:
            _write_shot_wardrobe_state(shot, prev_state)
            st = prev_state
            filled.append(sid)

        if undress:
            r = wardrobe_undress_rank(st)
            # Still full/armored while undressing → at least partial mid-strip
            if r is None or r < WARDROBE_UNDRESS_RANK["partial"]:
                _write_shot_wardrobe_state(shot, "partial")
                st = "partial"
                bumped.append(sid)
            # Undress action on max: prefer undressed when already partial
            elif auto_escalate and scale == "max" and r < WARDROBE_UNDRESS_RANK["undressed"]:
                _write_shot_wardrobe_state(shot, "undressed")
                st = "undressed"
                bumped.append(sid)

        if st is None and scale in {"max", "hot"} and ph in SEX_PHASES:
            # Sex beat with no evidence: default undressed (must not stay armored)
            target = "bare" if ph == "climax" else "undressed"
            _write_shot_wardrobe_state(shot, target)
            st = target
            filled.append(sid)

        # IRON: phase floor — 能脱就脱 / 能露就露 (only raise, never lower)
        if auto_escalate and scale in {"max", "hot"}:
            floor_state = PHASE_WARDROBE_FLOOR.get(ph)
            if floor_state:
                fr = wardrobe_undress_rank(floor_state)
                sr = wardrobe_undress_rank(st)
                if fr is not None and (sr is None or sr < fr):
                    _write_shot_wardrobe_state(shot, floor_state)
                    st = floor_state
                    escalated.append(
                        {
                            "id": sid,
                            "from": from_state or "none",
                            "to": floor_state,
                            "reason": f"phase_floor:{ph}",
                        }
                    )

        # Clamp re-dress: never allow rank below film peak so far
        if clamp_re_dress and st is not None and peak_state is not None:
            pr = wardrobe_undress_rank(peak_state)
            sr = wardrobe_undress_rank(st)
            if pr is not None and sr is not None and sr < pr:
                _write_shot_wardrobe_state(shot, peak_state)
                st = peak_state
                clamped.append(f"{sid}->{peak_state}")

        if st is not None:
            pr = wardrobe_undress_rank(prev_state)
            sr = wardrobe_undress_rank(st)
            if pr is None or (sr is not None and sr >= pr):
                prev_state = st
            # peak always advances to most undressed so far
            pkr = wardrobe_undress_rank(peak_state)
            if pkr is None or (sr is not None and sr > pkr) or peak_state is None:
                peak_state = st
        elif prev_state is not None:
            pass

        # Start-pose continuity: next beat must OPEN already undressed if peak says so
        if st in {"partial", "undressed", "bare"}:
            _ensure_start_pose_wardrobe(shot, st)
            start_pose_filled.append(sid)
            # Story serial: mark continue so register-clip auto-promotes last→first
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            if not dsl.get("chain_mode"):
                dsl["chain_mode"] = "continue"
                shot["dsl"] = dsl
            # end_pose should declare feeds-next for frame-chain lint
            end = str(dsl.get("end_pose") or "").strip()
            if not end:
                dsl["end_pose"] = f"holds undress state={st} mid-motion — feeds next first frame"
            elif "feed" not in end.lower():
                dsl["end_pose"] = f"{end} — feeds next first frame"

    return {
        "filled_ids": filled,
        "bumped_ids": bumped,
        "clamped_ids": clamped,
        "escalated": escalated,
        "start_pose_ids": start_pose_filled,
        "final_peak": peak_state or prev_state,
        "clamp_re_dress": bool(clamp_re_dress),
        "auto_escalate": bool(auto_escalate),
        "note": (
            "wardrobe continuity IRON: inherit; undress bump; phase floor "
            "foreplay≥partial act≥undressed climax≥bare; clamp re-dress; never reappear"
        ),
    }


def _ensure_start_pose_wardrobe(shot: dict[str, Any], state: str) -> None:
    """Force dsl.start_pose / subject to acknowledge already-undressed entry."""
    dsl = shot.get("dsl")
    if not isinstance(dsl, dict):
        dsl = {}
        shot["dsl"] = dsl
    hint = _WARDROBE_START_POSE_HINT.get(state, "")
    start = str(dsl.get("start_pose") or "").strip()
    low = start.lower()
    # If start_pose missing or still describes full dress, rewrite prefix
    fullish = any(
        m in low
        for m in (
            "fully clothed",
            "full wardrobe",
            "full costume",
            "full armor",
            "neat dress",
            "全装",
            "衣着整齐",
            "intact outfit",
        )
    )
    if not start:
        dsl["start_pose"] = hint
    elif fullish or (
        state in {"undressed", "bare"}
        and not any(
            m in low
            for m in (
                "undress",
                "bare",
                "nude",
                "半裸",
                "stripped",
                "already",
                "prior",
                "from prior",
            )
        )
    ):
        dsl["start_pose"] = f"{hint}; {start}"
    # Subject: if still "full wardrobe" while bare/undressed, tag conflict for lint
    subj = str(dsl.get("subject") or "")
    subj_l = subj.lower()
    if state in {"undressed", "bare", "partial"} and any(
        m in subj_l
        for m in (
            "full wardrobe",
            "fully clothed",
            "full costume",
            "full armor intact",
            "complete armor",
            "全装",
            "衣着整齐",
        )
    ):
        shot["_wardrobe_subject_conflict"] = True
        # Soft rewrite: prepend undress continuity token (keep face/identity words)
        prefix = {
            "partial": "half-undressed partial clothes disordered, ",
            "undressed": "undressed bare skin main outfit off, ",
            "bare": "bare exposed body, clothes discarded, ",
        }.get(state, "")
        if prefix and prefix.strip(", ") not in subj_l:
            dsl["subject"] = prefix + subj


def lint_sex_wardrobe(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
    require_strong: bool | None = None,
) -> dict[str, Any]:
    """Sex shots must not stay fully armored/clothed; undress beat required on max.

    Product rule (2026-07-21 / **IRON 2026-07-24**): 办事 = 卸甲/脱衣 → 裸露可读。
    act/climax wardrobe_state must be undressed|bare on max (strong); climax must reach bare.
    At least one undress-action beat in foreplay or early act.
    Continuity: wardrobe rank monotonic — **衣服不回穿** (HEAT_WARDROBE_RE_DRESS).
    """
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    hardcore = profile in {"hardcore_male", "hardcore", "重口男向"}
    if require_strong is None:
        # max IRON: strong wardrobe by default (not only hardcore)
        require_strong = hardcore or scale == "max"
    ok_states = SEX_WARDROBE_STRONG if require_strong else SEX_WARDROBE_OK

    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    per_shot: list[dict[str, Any]] = []
    sex_shots: list[tuple[dict[str, Any], str]] = []
    undress_beats: list[str] = []
    re_dress_ids: list[str] = []
    text_conflict_ids: list[str] = []
    bare_peak_ok = True

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    peak_rank = -1
    peak_state: str | None = None
    peak_sid: str | None = None
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "")
        ph = infer_heat_phase(shot)
        st = resolve_wardrobe_state(shot)
        undress = shot_has_undress_action(shot)
        rank = wardrobe_undress_rank(st)
        row = {
            "id": sid,
            "heat_phase": ph,
            "wardrobe_state": st,
            "undress_action": undress,
            "undress_rank": rank,
        }
        # Monotonic: known state cannot drop below peak undress so far
        if rank is not None and peak_rank >= 0 and rank < peak_rank:
            re_dress_ids.append(f"{sid}:{st}<{peak_state}(from {peak_sid or '?'})")
            row["re_dress"] = True
        if rank is not None and rank > peak_rank or rank is not None and peak_rank < 0:
            peak_rank = rank
            peak_state = st
            peak_sid = sid or None

        # Text conflict: wardrobe_state says bare but dsl.subject still "full wardrobe"
        if st in {"partial", "undressed", "bare"}:
            blob = _shot_visual_blob(shot)
            if shot.get("_wardrobe_subject_conflict") or any(
                m in blob for m in _FULL_DRESS_MARKERS
            ):
                # only flag if full-dress markers present without undress override words
                if any(m in blob for m in _FULL_DRESS_MARKERS) and not any(
                    m in blob
                    for m in (
                        "already undressed",
                        "from prior",
                        "clothes discarded",
                        "outfit off",
                        "half-undressed",
                    )
                ):
                    text_conflict_ids.append(f"{sid}:{st}+full_dress_text")
                    row["text_conflict"] = True

        per_shot.append(row)
        if undress and ph in {"foreplay", "act", "setup"}:
            undress_beats.append(sid or ph)
        if ph in SEX_PHASES:
            sex_shots.append((shot, ph))

    if scale not in {"max", "hot"}:
        # Still report re-dress / text conflict if any
        if re_dress_ids:
            _issue(
                "HEAT_WARDROBE_RE_DRESS",
                "warning",
                "wardrobe re-dressed mid-film (衣服回穿) — "
                f"{', '.join(re_dress_ids[:8])}"
                + ("…" if len(re_dress_ids) > 8 else "")
                + "。卸装状态只可前进 full→armored→partial→undressed→bare，"
                "后镜必须延续前镜；禁止穿回。",
            )
        if text_conflict_ids:
            _issue(
                "HEAT_WARDROBE_TEXT_CONFLICT",
                "warning",
                "wardrobe_state undressed/bare but dsl.subject still describes full dress — "
                f"{', '.join(text_conflict_ids[:8])}"
                + "。下一镜开头必须用已脱状态，禁 full wardrobe 字样。",
            )
        warn_n = sum(1 for i in issues if i.get("severity") == "warning")
        return {
            "ok": warn_n == 0,
            "codes": sorted(set(codes)),
            "warning_count": warn_n,
            "info_count": 0,
            "issues": issues,
            "heat_scale": scale,
            "sex_shot_count": len(sex_shots),
            "undress_beats": undress_beats,
            "re_dress_shots": re_dress_ids,
            "text_conflict_shots": text_conflict_ids,
            "per_shot": per_shot,
            "required_states": sorted(ok_states),
            "peak_state": peak_state,
            "note": "wardrobe continuity checked; sex ladder skipped (no max/hot)",
        }

    if not sex_shots and not re_dress_ids and not text_conflict_ids:
        return {
            "ok": True,
            "codes": [],
            "warning_count": 0,
            "info_count": 0,
            "issues": [],
            "heat_scale": scale,
            "sex_shot_count": 0,
            "undress_beats": undress_beats,
            "re_dress_shots": [],
            "text_conflict_shots": [],
            "per_shot": per_shot,
            "required_states": sorted(ok_states),
            "peak_state": peak_state,
            "note": "wardrobe sex lint skipped (no max/hot sex phases)",
        }

    dressed_ids: list[str] = []
    weak_ids: list[str] = []
    for shot, ph in sex_shots:
        sid = str(shot.get("id") or "?")
        st = resolve_wardrobe_state(shot)
        blob = _shot_visual_blob(shot)
        exposed = any(m in blob for m in _EXPOSED_WARDROBE_MARKERS)
        if st in {"full", "armored"} or (
            st is None and not exposed and any(m in blob for m in _FULL_DRESS_MARKERS)
        ):
            dressed_ids.append(f"{sid}:{st or 'full?'}")
        elif st is None and not exposed:
            # act/climax with no wardrobe evidence → treat as still-clothed risk
            dressed_ids.append(f"{sid}:unspecified")
        elif st is not None and st not in ok_states:
            weak_ids.append(f"{sid}:{st}")
        elif require_strong and st == "partial":
            weak_ids.append(f"{sid}:partial")

    if dressed_ids:
        _issue(
            "HEAT_SEX_WARDROBE_DRESSED",
            "warning",
            "act/climax still fully clothed/armored or wardrobe unspecified — "
            f"{', '.join(dressed_ids[:8])}"
            + ("…" if len(dressed_ids) > 8 else "")
            + "。办事镜必须卸甲/脱衣到 partial|undressed|bare（写 wardrobe_state 或 "
            "dsl 写 bare skin / armor off / 半裸 / 卸甲）。禁止全装铠甲跨坐冒充办事。",
        )
    if weak_ids and require_strong:
        _issue(
            "HEAT_SEX_WARDROBE_WEAK",
            "warning",
            "max IRON: act/climax wardrobe only partial — must be undressed|bare "
            f"({', '.join(weak_ids[:8])})",
        )
    # Bare peak: max films with sex must expose bare at least once (能露点就要露点)
    climax_not_bare: list[str] = []
    for shot, ph in sex_shots:
        if ph != "climax":
            continue
        sid = str(shot.get("id") or "?")
        st = resolve_wardrobe_state(shot)
        if st != "bare":
            climax_not_bare.append(f"{sid}:{st or 'none'}")
    if sex_shots:
        bare_peak_ok = peak_state == "bare" or any(
            resolve_wardrobe_state(sh) == "bare" for sh, _ph in sex_shots if isinstance(sh, dict)
        )
    if scale == "max" and sex_shots and DEFAULT_BARE_PEAK_REQUIRED and not bare_peak_ok:
        _issue(
            "HEAT_BARE_PEAK_MISSING",
            "warning",
            "max IRON: film never reaches wardrobe_state=bare — "
            "climax (and peak act) must expose bare/readable nudity. "
            "能露点就要露点；set climax wardrobe_state=bare.",
        )
    elif scale == "max" and climax_not_bare:
        _issue(
            "HEAT_BARE_PEAK_MISSING",
            "warning",
            "max IRON: climax shot(s) not bare — "
            f"{', '.join(climax_not_bare[:8])}. climax must be wardrobe_state=bare.",
        )
    if not undress_beats and sex_shots:
        _issue(
            "HEAT_UNDRESS_BEAT_MISSING",
            "warning",
            "no undress/卸甲 action beat found before or during act — "
            "add a foreplay/act shot that visibly removes armor/clothes "
            "(dsl.action: removes armor / strips / 脱下 / 卸甲). "
            "Sex must not jump from full costume to climax without undress.",
        )
    if re_dress_ids:
        _issue(
            "HEAT_WARDROBE_RE_DRESS",
            "warning",
            "wardrobe re-dressed after undress (衣服回穿) — "
            f"{', '.join(re_dress_ids[:8])}"
            + ("…" if len(re_dress_ids) > 8 else "")
            + "。分镜必须延续前镜卸装状态；rank 只可前进 "
            "full→armored→partial→undressed→bare。禁止 afterglow/后续镜穿回全装。"
            "下一镜 start_pose/subject 必须从已脱状态开场。",
        )
    if text_conflict_ids:
        _issue(
            "HEAT_WARDROBE_TEXT_CONFLICT",
            "warning",
            "wardrobe_state undressed/bare/partial but dsl.subject still full-dress — "
            f"{', '.join(text_conflict_ids[:8])}"
            + ("…" if len(text_conflict_ids) > 8 else "")
            + "。改 subject/start_pose：写 already undressed / bare skin / clothes discarded，"
            "禁 full wardrobe 当办事后镜开场。",
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "warning_count": warn_n,
        "info_count": sum(1 for i in issues if i.get("severity") == "info"),
        "issues": issues,
        "heat_scale": scale,
        "audience_profile": profile,
        "sex_shot_count": len(sex_shots),
        "undress_beats": undress_beats,
        "dressed_sex_shots": dressed_ids,
        "weak_sex_shots": weak_ids,
        "re_dress_shots": re_dress_ids,
        "text_conflict_shots": text_conflict_ids,
        "per_shot": per_shot,
        "required_states": sorted(ok_states),
        "peak_state": peak_state,
        "bare_peak_ok": bare_peak_ok,
        "note": (
            "Sex wardrobe IRON: full→partial→undressed→bare. "
            "max act+ = undressed|bare; climax = bare; undress beat required; "
            "continuity monotonic (衣服不回穿). "
            "See lessons-2026-07-21-sex-undress-ladder.md · adult-max iron 2026-07-24"
        ),
    }


# Adult-max template pollution (金瓶梅案 · 2026-07-22)
# When ≥40% of voiced nars are these stock lines, user script was overwritten.
_TEMPLATE_NAR_POLLUTION_MARKERS: tuple[str, ...] = (
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
    "扣子崩开。半裸卸甲",
)


def is_template_nar_pollution(nar: object) -> bool:
    text = str(nar or "").strip()
    if not text:
        return False
    return any(m in text for m in _TEMPLATE_NAR_POLLUTION_MARKERS)


def lint_user_source_fidelity(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    source_excerpt: str | None = None,
) -> dict[str, Any]:
    """Fail when plan/spice templates wiped user story language.

    Product rule (2026-07-22): user input is the spine; spice templates are
    fallback seeds only. Independent multi-section scripts must not become
    3×「展厅落锁」clones.
    """
    scale = (heat_scale or "").strip().lower() or None
    excerpt = (source_excerpt or "").strip()
    # This lint protects supplied source language; a generated/stock plan has
    # no user source to preserve. Do not mistake its own VO for overwritten text.
    if not excerpt:
        return {
            "ok": True,
            "applicable": False,
            "codes": [],
            "warning_count": 0,
            "issues": [],
            "polluted_shots": [],
            "pollution_ratio": 0.0,
            "voiced": 0,
            "note": "user source fidelity skipped: source_excerpt is absent",
        }
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    polluted: list[str] = []
    voiced = 0
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        nar = str(shot.get("nar") or "").strip()
        if not nar:
            continue
        voiced += 1
        if is_template_nar_pollution(nar):
            polluted.append(str(shot.get("id") or "?"))

    ratio = (len(polluted) / voiced) if voiced else 0.0
    # Only flag when we have enough voiced shots and high template density
    if voiced >= 4 and ratio + 1e-9 >= 0.40:
        codes.append("USER_SOURCE_NAR_POLLUTED")
        issues.append(
            {
                "code": "USER_SOURCE_NAR_POLLUTED",
                "severity": "warning",
                "message": (
                    f"旁白模板污染 {ratio:.0%}（{len(polluted)}/{voiced}）含「展厅落锁/加演」等库存句 — "
                    "用户原文被 adult-max 模板覆盖。须保留用户诗白/对白/专有名词，"
                    "荤梗只能补后缀不能整句替换。See lessons-2026-07-22-user-source-fidelity.md"
                ),
            }
        )
    # If source excerpt has unique story tokens missing from all nars → soft warn
    if excerpt and voiced >= 3 and scale in {"max", "hot"}:
        # sample distinctive CJK 2-grams from source that should appear somewhere
        tokens = re.findall(r"[\u4e00-\u9fff]{2,4}", excerpt)
        skip = {
            "成人",
            "办事",
            "竖屏",
            "短剧",
            "旁白",
            "镜头",
            "特写",
            "时长",
            "开场",
            "转场",
            "集尾",
        }
        distinctive = []
        for t in tokens:
            if t in skip or t in _TEMPLATE_NAR_POLLUTION_MARKERS:
                continue
            if t not in distinctive:
                distinctive.append(t)
            if len(distinctive) >= 12:
                break
        all_nar = " ".join(str(s.get("nar") or "") for s in shots if isinstance(s, dict))
        missing = [t for t in distinctive[:8] if t not in all_nar]
        if len(missing) >= 4 and ratio >= 0.25:
            codes.append("USER_SOURCE_TOKENS_MISSING")
            issues.append(
                {
                    "code": "USER_SOURCE_TOKENS_MISSING",
                    "severity": "warning",
                    "message": (
                        "用户剧本专名/情节点未进入旁白: "
                        + "、".join(missing[:6])
                        + "。plan 后须对照 source 回填 nar，禁止只用库存荤梗。"
                    ),
                }
            )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "applicable": True,
        "codes": sorted(set(codes)),
        "warning_count": warn_n,
        "issues": issues,
        "polluted_shots": polluted,
        "pollution_ratio": round(ratio, 3),
        "voiced": voiced,
        "note": "user source fidelity: lessons-2026-07-22-user-source-fidelity.md",
    }


def nar_has_spice(nar: object) -> bool:
    text = str(nar or "").strip().lower()
    if not text:
        return False
    return any(m.lower() in text for m in _NAR_SPICE_MARKERS)


def nar_has_sex_verb(nar: object) -> bool:
    text = str(nar or "").strip().lower()
    if not text:
        return False
    return any(m.lower() in text for m in _NAR_SEX_VERB_MARKERS)


def nar_has_extreme_spice(nar: object) -> bool:
    """True if nar hits denser body/sex markers (not dual-entendre alone)."""
    text = str(nar or "").strip().lower()
    if not text:
        return False
    return any(m.lower() in text for m in _NAR_EXTREME_MARKERS)


def normalize_spice_level(
    value: object | None,
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
) -> str | None:
    raw = str(value or "").strip().lower() or None
    if raw in SPICE_LEVELS:
        return raw
    if raw:
        return None  # invalid left to caller
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    if profile in {"hardcore_male", "hardcore", "重口男向"}:
        return "extreme"
    if scale == "max":
        return "extreme"  # adult max IRON · 2026-07-24 (was explicit)
    if scale == "hot":
        return "suggestive"
    return None


def resolve_sex_pose(shot: dict[str, Any]) -> str | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = str(shot.get("sex_pose") or dsl.get("sex_pose") or "").strip().lower()
    if raw in SEX_POSES:
        return raw
    # infer from coitus beat / action
    cb = resolve_coitus_beat(shot)
    if cb and cb in COITUS_BEAT_DEFAULT_POSE:
        blob = _shot_visual_pose_blob(shot)
        # keep inferred pose only when coitus-ish
        if any(m in blob for m in _COITUS_READABLE_MARKERS) or cb in COITUS_BEATS:
            return COITUS_BEAT_DEFAULT_POSE[cb]
    return None


def lint_sex_vo_spice(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
    spice_level: str | None = None,
) -> dict[str, Any]:
    """Adult max films: every nar must carry 荤梗; act/climax need sex verbs.

    Product rule (2026-07-21): 实打实办事剧 — 讲的内容都要荤梗，禁纯文艺说书。
    v1.10: spice_level=extreme → dual-entendre alone is HEAT_VO_SPICE_TOO_MILD.
    """
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    level = normalize_spice_level(spice_level, heat_scale=scale, audience_profile=profile)
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    per_shot: list[dict[str, Any]] = []
    bland: list[str] = []
    weak_sex: list[str] = []
    too_mild: list[str] = []
    spice_n = 0
    extreme_n = 0
    voiced_n = 0

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"}:
        return {
            "ok": True,
            "codes": [],
            "warning_count": 0,
            "info_count": 0,
            "issues": [],
            "heat_scale": scale,
            "spice_level": level,
            "spice_ratio": None,
            "bland_shots": [],
            "weak_sex_vo_shots": [],
            "too_mild_shots": [],
            "per_shot": [],
            "note": "VO spice lint skipped (not max/hot)",
        }

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "")
        ph = infer_heat_phase(shot)
        nar = str(shot.get("nar") or "").strip()
        if not nar:
            continue
        voiced_n += 1
        spice = nar_has_spice(nar)
        sex_v = nar_has_sex_verb(nar)
        extreme = nar_has_extreme_spice(nar)
        literary = any(h in nar for h in _NAR_LITERARY_ONLY_HINTS)
        if spice:
            spice_n += 1
        if extreme:
            extreme_n += 1
        row = {
            "id": sid,
            "heat_phase": ph,
            "spice": spice,
            "sex_verb": sex_v,
            "extreme": extreme,
            "literary_hint": literary,
        }
        per_shot.append(row)
        if not spice:
            bland.append(sid or "?")
        if ph in SEX_PHASES and not sex_v:
            weak_sex.append(sid or "?")
        # extreme: act/climax with only mild dual-entendre fail
        # setup/foreplay/afterglow may stay dual-entendre + light body words
        if level == "extreme" and ph in SEX_PHASES and spice and not extreme:
            too_mild.append(sid or "?")

    spice_ratio = (spice_n / voiced_n) if voiced_n else 1.0
    extreme_ratio = (extreme_n / voiced_n) if voiced_n else 1.0

    if bland:
        _issue(
            "HEAT_VO_SPICE_MISSING",
            "warning",
            "旁白缺荤梗（实打实办事剧禁纯文艺）: "
            f"{', '.join(bland[:10])}"
            + ("…" if len(bland) > 10 else "")
            + "。每镜 nar 须含身体/办事/双关词（沉腰/办穿/加演/换你顶/腿软/吃进…）。"
            "See lessons-2026-07-21-sex-vo-spice.md",
        )
    if weak_sex:
        _issue(
            "HEAT_VO_SEX_VERB_WEAK",
            "warning",
            "act/climax 旁白缺办事动词: "
            f"{', '.join(weak_sex[:10])}"
            + ("…" if len(weak_sex) > 10 else "")
            + "。要用沉腰/顶/磨/骑/办穿/办完/吃进/锁腰/高潮/换你顶 等同画面动词，"
            "禁只写灯灭/回眸/故事开始。",
        )
    # max: require full coverage (every voiced shot spicy); hot: ≥70%
    need = 1.0 if scale == "max" else 0.70
    if voiced_n >= 3 and spice_ratio + 1e-9 < need and not bland:
        # bland already covers missing; this is aggregate safety
        pass
    if scale == "max" and voiced_n >= 4 and spice_ratio + 1e-9 < 0.85:
        _issue(
            "HEAT_VO_SPICE_RATIO_LOW",
            "warning",
            f"荤梗覆盖 {spice_ratio:.0%} < 85%（max 办事剧目标全覆盖）—"
            f"{spice_n}/{voiced_n} 镜。重写 bland 旁白。",
        )
    if profile in {"hardcore_male", "hardcore", "重口男向"} and weak_sex:
        # already issued HEAT_VO_SEX_VERB_WEAK; keep
        pass
    if too_mild:
        _issue(
            "HEAT_VO_SPICE_TOO_MILD",
            "warning",
            "spice_level=extreme 但旁白仍偏双关/不够脏: "
            f"{', '.join(too_mild[:10])}"
            + ("…" if len(too_mild) > 10 else "")
            + "。act/climax 须直白办事动词（沉腰/吃进/办穿/顶/插…），禁只写加演/规矩/夜色。",
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "warning_count": warn_n,
        "info_count": sum(1 for i in issues if i.get("severity") == "info"),
        "issues": issues,
        "heat_scale": scale,
        "audience_profile": profile,
        "spice_level": level,
        "spice_ratio": round(spice_ratio, 3),
        "extreme_ratio": round(extreme_ratio, 3),
        "spice_n": spice_n,
        "voiced_n": voiced_n,
        "bland_shots": bland,
        "weak_sex_vo_shots": weak_sex,
        "too_mild_shots": too_mild,
        "per_shot": per_shot,
        "note": (
            "max adult: 荤梗 + sex verbs; extreme rejects dual-entendre-only act VO. "
            "sex_vo_strict on max. lessons-2026-07-21-sex-vo-spice.md"
        ),
    }


def _shot_visual_pose_blob(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    bits = [
        str(shot.get("sex_pose") or ""),
        str(shot.get("coitus_beat") or dsl.get("coitus_beat") or ""),
        str(dsl.get("action") or ""),
        str(dsl.get("motion") or ""),
        str(dsl.get("visible_change") or ""),
        str(dsl.get("subject") or ""),
        str(shot.get("must_show") or ""),
        str(shot.get("nar") or ""),
    ]
    return " ".join(bits).lower()


def shot_coitus_readable(shot: dict[str, Any]) -> bool:
    """Mute-frame proxy: action language includes coitus-readable pose verbs."""
    blob = _shot_visual_pose_blob(shot)
    if not blob.strip():
        return False
    has_real = any(m in blob for m in _COITUS_READABLE_MARKERS)
    if not has_real:
        return False
    # pure pseudo without real markers already failed; if only soft words dominate, still ok if real present
    return True


def shot_coitus_pseudo_only(shot: dict[str, Any]) -> bool:
    blob = _shot_visual_pose_blob(shot)
    if any(m in blob for m in _COITUS_READABLE_MARKERS):
        return False
    return any(m in blob for m in _COITUS_PSEUDO_ONLY) or bool(blob.strip())


def resolve_coitus_beat(shot: dict[str, Any]) -> str | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = shot.get("coitus_beat") or dsl.get("coitus_beat") or shot.get("sex_beat")
    if raw and str(raw).strip().lower() in COITUS_BEATS:
        return str(raw).strip().lower()
    # Infer from pose blob
    blob = _shot_visual_pose_blob(shot)
    if any(
        x in blob for x in ("arch-finish", "arch finish", "办穿", "失声", "residual-tremor", "高潮")
    ):
        return "finish"
    if any(x in blob for x in ("leg-wrap", "clutch", "锁腰", "锁腿", "攥")):
        return "lock"
    if any(x in blob for x in ("hips-sink", "grind", "rhythm", "沉腰", "顶", "磨")):
        return "rhythm"
    if any(
        x in blob
        for x in (
            "deep thrust",
            "deep-thrust",
            "penetrating thrust",
            "penetrating-thrust",
            "bottoming out",
            "bottoming-out",
        )
    ):
        return "deep_thrust"
    if any(
        x in blob
        for x in (
            "internal ejaculation",
            "internal-ejaculation",
            "internal peak",
            "internal-peak",
            "overflow",
            "溢出",
            "残留",
            "高潮",
        )
    ):
        return "internal_peak"
    if any(
        x in blob
        for x in (
            "creampie",
            "creampie release",
            "creampie-release",
            "biological fluid",
            "biological release",
            "biological fluid",
            "leaking",
            "渗",
        )
    ):
        return "creampie_release"
    if any(x in blob for x in ("straddle", "mount", "pelvis-lock", "跨坐", "结合", "union")):
        return "union"
    if any(x in blob for x in ("pin", "entry", "拽", "压进", "按进")):
        return "entry"
    if any(x in blob for x in ("undress", "strip", "卸甲", "脱", "肩带")):
        return "undress"
    if any(x in blob for x in ("换你顶", "下一场", "未完", "whisper", "hook")):
        return "hook"
    return None


def lint_coitus_grammar(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
    coitus_grammar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Intercourse six-beat coverage + mute-frame pose readability (docs → code)."""
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    cg = coitus_grammar if isinstance(coitus_grammar, dict) else {}
    enabled = cg.get("enabled")
    if enabled is None:
        enabled = scale == "max" or profile in {"hardcore_male", "hardcore", "重口男向"}
    enabled = bool(enabled)

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if not enabled or scale not in {"max", "hot"}:
        return {
            "ok": True,
            "enabled": False,
            "codes": [],
            "issues": [],
            "beats_covered": {},
            "readable_act_ratio": None,
            "note": "coitus grammar skipped (not max/hot or disabled)",
        }

    hardcore = profile in {"hardcore_male", "hardcore", "重口男向"}
    sev = "warning"  # film_spec may promote via coitus_strict

    # Map beats → shot ids from explicit grammar or per-shot fields
    beats_map: dict[str, list[str]] = {b: [] for b in COITUS_REQUIRED_BEATS}
    beats_map["undress"] = []
    explicit = cg.get("beats") if isinstance(cg.get("beats"), dict) else {}
    for b, ids in explicit.items():
        bk = str(b).strip().lower()
        if bk not in beats_map:
            continue
        if isinstance(ids, list):
            beats_map[bk] = [str(x) for x in ids if str(x).strip()]
        elif ids:
            beats_map[bk] = [str(ids)]

    act_shots: list[dict[str, Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        ph = infer_heat_phase(shot)
        sid = str(shot.get("id") or "")
        cb = resolve_coitus_beat(shot)
        if cb and sid and sid not in beats_map.get(cb, []):
            beats_map.setdefault(cb, []).append(sid)
        if ph in SEX_PHASES:
            act_shots.append(shot)

    missing = [b for b in COITUS_REQUIRED_BEATS if not beats_map.get(b)]
    # Six-beat: hardcore always; max requires core union+rhythm+finish at warning;
    # full six when grammar.enabled explicitly or hardcore
    core_missing = [b for b in ("union", "rhythm", "finish") if not beats_map.get(b)]
    if missing and (hardcore or bool(cg.get("enabled"))):
        _issue(
            "COITUS_BEAT_MISSING",
            sev,
            f"coitus six-beat missing: {','.join(missing)} — "
            "assign coitus_beat or coitus_grammar.beats "
            "(entry/union/rhythm/lock/finish/hook). See intercourse-impact-benchmark.",
        )
    elif core_missing and scale == "max" and act_shots:
        _issue(
            "COITUS_BEAT_MISSING",
            sev,
            f"max IRON coitus core missing: {','.join(core_missing)} — "
            "need union + rhythm + finish (抽送+结合+高潮) at minimum.",
        )

    unreadable: list[str] = []
    pseudo: list[str] = []
    for shot in act_shots:
        sid = str(shot.get("id") or "?")
        if shot_coitus_readable(shot):
            continue
        if shot_coitus_pseudo_only(shot):
            pseudo.append(sid)
        unreadable.append(sid)

    readable_n = len(act_shots) - len(unreadable)
    ratio = (readable_n / len(act_shots)) if act_shots else 1.0
    # Unreadable pose: hardcore always; max IRON when majority unreadable
    if act_shots and hardcore and ratio + 1e-9 < 0.50:
        _issue(
            "COITUS_UNREADABLE_POSE",
            sev,
            f"act/climax coitus-readable ratio {ratio:.0%} "
            f"(unreadable={unreadable[:8]}) — use straddle/hips-sink/grind/pelvis-lock; "
            "forbid hug-only soft lean as act main. Mute Frame Test.",
        )
    elif act_shots and scale == "max" and ratio + 1e-9 < 0.50 and unreadable:
        _issue(
            "COITUS_UNREADABLE_POSE",
            sev,
            f"max IRON: act coitus-readable {ratio:.0%} "
            f"(unreadable={unreadable[:8]}) — 静音一帧须可读办事，禁拥抱冒充。",
        )
    elif act_shots and not hardcore and ratio + 1e-9 < 0.50 and unreadable:
        _issue(
            "COITUS_UNREADABLE_POSE",
            "info" if not bool(cg.get("enabled")) else sev,
            f"advisory: act coitus-readable {ratio:.0%} — strengthen pose verbs for impact",
        )
    if pseudo and (hardcore or scale == "max"):
        _issue(
            "COITUS_PSEUDO_SEX",
            sev,
            f"pseudo-sex pose language only: {pseudo[:6]} — embrace/牵手 is not coitus",
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "enabled": True,
        "codes": sorted(set(codes)),
        "issues": issues,
        "beats_covered": {k: v for k, v in beats_map.items() if v},
        "missing_beats": missing,
        "act_shot_count": len(act_shots),
        "readable_act_ratio": round(ratio, 3),
        "unreadable_shots": unreadable,
        "pseudo_shots": pseudo,
        "note": "coitus grammar: six-beat + mute-frame pose verbs. lessons-2026-07-21-intercourse-impact-benchmark.md",
    }


# --- Sex arc 起承转合 (P0 · 2026-07-27 adult-scale-max-sex-arc) ---
# Product four-beat: foreplay(起) → entry(承) → penetration(转) → climax_release(合)
SEX_ARC_BEATS = frozenset({"foreplay", "entry", "penetration", "climax_release", "afterglow"})
SEX_ARC_REQUIRED = ("foreplay", "penetration", "climax_release")
_SEX_ARC_PENETRATION_MARKERS: tuple[str, ...] = (
    "hips-sink",
    "hip-sink",
    "grind",
    "thrust",
    "deep thrust",
    "deep-thrust",
    "penetrating thrust",
    "penetrating-thrust",
    "bottoming out",
    "bottoming-out",
    "straddle",
    "mount",
    "pelvis",
    "union",
    "penetration",
    "insert",
    "沉腰",
    "顶弄",
    "顶撞",
    "抽送",
    "纳入",
    "插入",
    "办穿",
    "吃进",
    "跨坐",
    "结合",
    "体内",
)
_SEX_ARC_RELEASE_MARKERS: tuple[str, ...] = (
    "climax",
    "finish",
    "arch-finish",
    "release",
    "ejaculat",
    "cum",
    "orgasm",
    "internal ejaculation",
    "internal-ejaculation",
    "internal peak",
    "internal-peak",
    "creampie",
    "creampie release",
    "creampie-release",
    "overflow",
    "overflowing",
    "biological fluid",
    "biological release",
    "高潮",
    "射出",
    "失声",
    "痉挛",
    "办穿",
    "residual",
    "tremor",
    "体内",
    "残留",
    "溢出",
    "渗",
)
_SEX_ARC_FOREPLAY_MARKERS: tuple[str, ...] = (
    "undress",
    "strip",
    "kiss",
    "caress",
    "foreplay",
    "肩带",
    "解衣",
    "脱",
    "贴身",
    "摩擦",
    "亲吻",
    "前戏",
    "卸甲",
)


def resolve_sex_arc_beat(shot: dict[str, Any]) -> str | None:
    """Map shot → sex_arc_beat (explicit field, coitus_beat, or phase/markers)."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = (
        shot.get("sex_arc_beat")
        or dsl.get("sex_arc_beat")
        or shot.get("sex_arc_role")
        or dsl.get("sex_arc_role")
    )
    if raw:
        s = str(raw).strip().lower()
        # role aliases
        role_map = {
            "setup": "foreplay",
            "build": "entry",
            "turn": "penetration",
            "resolve": "climax_release",
        }
        if s in SEX_ARC_BEATS:
            return s
        if s in role_map:
            return role_map[s]
    # coitus six-beat → four-beat
    cb = resolve_coitus_beat(shot)
    if cb in {"undress"}:
        return "foreplay"
    if cb in {"entry", "hook"}:
        return "entry" if cb == "entry" else "afterglow"
    if cb in {"union", "rhythm", "lock", "entry", "deep_thrust"}:
        return "penetration"
    if cb in {"finish", "internal_peak", "creampie_release"}:
        return "climax_release"
    ph = infer_heat_phase(shot)
    blob = _shot_visual_pose_blob(shot)
    if ph == "foreplay" or any(m in blob for m in _SEX_ARC_FOREPLAY_MARKERS):
        if ph in SEX_PHASES and any(m in blob for m in _SEX_ARC_PENETRATION_MARKERS):
            return "penetration"
        if ph == "foreplay" or (
            ph == "setup" and any(m in blob for m in _SEX_ARC_FOREPLAY_MARKERS)
        ):
            return "foreplay"
    # climax phase alone is NOT climax_release — need explicit release markers
    if any(m in blob for m in _SEX_ARC_RELEASE_MARKERS) or (resolve_coitus_beat(shot) == "finish"):
        return "climax_release"
    if ph in SEX_PHASES:
        if any(m in blob for m in _SEX_ARC_PENETRATION_MARKERS):
            return "penetration"
        if any(m in blob for m in _SEX_ARC_RELEASE_MARKERS):
            return "climax_release"
        # IRON 2026-07-28: bare+act alone is NOT penetration (ban hug-as-sex false green)
    if ph == "afterglow":
        return "afterglow"
    if ph == "foreplay":
        return "foreplay"
    return None


def _shot_has_penetration_verb(shot: dict[str, Any]) -> bool:
    """True when act/penetration language is coitus-readable (not bare hug)."""
    cb = resolve_coitus_beat(shot)
    if cb in {"union", "rhythm", "lock", "entry", "deep_thrust"}:
        return True
    if shot_coitus_readable(shot):
        return True
    blob = _shot_visual_pose_blob(shot)
    return any(m in blob for m in _SEX_ARC_PENETRATION_MARKERS)


def _shot_has_release_marker(shot: dict[str, Any]) -> bool:
    cb = resolve_coitus_beat(shot)
    if cb in {"finish", "internal_peak", "creampie_release"}:
        return True
    raw = (
        str(shot.get("sex_arc_beat") or (shot.get("dsl") or {}).get("sex_arc_beat") or "")
        .strip()
        .lower()
    )
    if raw in {"climax_release", "resolve"}:
        return True
    blob = _shot_visual_pose_blob(shot)
    strong = (
        "高潮",
        "射出",
        "arch-finish",
        "ejaculat",
        "orgasm",
        "cum",
        "finish",
        "climax",
        "release",
        "失声",
        "痉挛",
        "residual-tremor",
        "residual tremor",
    )
    return any(m in blob for m in strong)


def _shot_duration_sec(shot: dict[str, Any], default: float = 6.0) -> float:
    try:
        return max(0.0, float(shot.get("duration_sec") or default))
    except (TypeError, ValueError):
        return default


def _is_detail_cu_shot(shot: dict[str, Any]) -> bool:
    """Union/genital/waist lock close-up or coverage_role=detail."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    role = (
        str(shot.get("coverage_role") or dsl.get("coverage_role") or shot.get("shot_role") or "")
        .strip()
        .lower()
    )
    framing = (
        str(shot.get("framing") or dsl.get("framing") or cam.get("framing") or "").strip().lower()
    )
    size = (
        str(cam.get("shot_size") or dsl.get("shot_size") or shot.get("shot_size") or "")
        .strip()
        .lower()
    )
    blob = f"{role} {framing} {size} {_shot_visual_pose_blob(shot)}"
    if role in {"detail", "insert", "ecu", "cu_insert"}:
        return True
    if any(
        x in framing
        for x in (
            "genital_lock",
            "union_closeup",
            "union_close",
            "waist_lock",
            "pelvis_cu",
            "hip_cu",
        )
    ):
        return True
    if any(
        x in blob
        for x in (
            "insert",
            "detail",
            "ecu",
            "extreme close",
            "局部",
            "定器",
            "结合部",
            "腰腹",
            "pelvis-lock",
            "pelvis lock",
            "union close",
        )
    ) and any(
        x in size or x in framing or x in role
        for x in ("close", "cu", "insert", "detail", "特写", "近景")
    ):
        return True
    if "close-up insert" in size or "closeup insert" in size:
        return True
    return False


def resolve_partner_wardrobe_state(shot: dict[str, Any]) -> str | None:
    """Partner/male lower-body wardrobe when present on shot or dsl."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = (
        shot.get("partner_wardrobe_state")
        or dsl.get("partner_wardrobe_state")
        or shot.get("partner_wardrobe")
        or dsl.get("partner_wardrobe")
    )
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip().lower()
    if s in WARDROBE_STATES:
        return s
    aliases = {
        "nude": "bare",
        "naked": "bare",
        "pants_off": "undressed",
        "bottomless": "undressed",
        "半脱": "partial",
        "脱尽": "bare",
        "下装脱尽": "undressed",
    }
    return aliases.get(s)


def lint_sex_detail_cu(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Require ≥1 union/waist detail CU in meat block (max)."""
    scale = (heat_scale or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    if scale != "max":
        return {
            "ok": True,
            "enabled": False,
            "codes": [],
            "issues": [],
            "detail_shots": [],
            "note": "sex detail CU skipped (not max)",
        }
    meat = [
        sh
        for sh in shots
        if isinstance(sh, dict) and infer_heat_phase(sh) in SEX_PHASES | {"foreplay"}
    ]
    if not any(infer_heat_phase(sh) in SEX_PHASES for sh in meat if isinstance(sh, dict)):
        return {
            "ok": True,
            "enabled": True,
            "codes": [],
            "issues": [],
            "detail_shots": [],
            "note": "no act/climax — detail CU N/A",
        }
    detail_ids = [
        str(sh.get("id") or "?") for sh in meat if isinstance(sh, dict) and _is_detail_cu_shot(sh)
    ]
    if not detail_ids:
        codes.append("SEX_DETAIL_CU_MISSING")
        issues.append(
            {
                "code": "SEX_DETAIL_CU_MISSING",
                "severity": "warning",
                "message": (
                    "meat block missing 定器/结合特写 — add ≥1 shot with "
                    "coverage_role=detail or framing=union_closeup|genital_lock "
                    "or camera.shot_size close-up insert (waist/pelvis). "
                    "禁全程只拍脸贴脸。See adult-scale-max-sex-arc."
                ),
            }
        )
    return {
        "ok": not codes,
        "enabled": True,
        "codes": codes,
        "issues": issues,
        "detail_shots": detail_ids,
        "note": "sex detail CU IRON: ≥1 union/waist lock close-up in meat",
    }


def lint_both_undress(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Penetration window: heroine bare + partner ≥undressed when field present.

    When partner_wardrobe_state is omitted on all penetration shots, emit soft
    SEX_BOTH_UNDRESS_UNSTATED (info). When present but weak → SEX_BOTH_UNDRESS_MISSING.
    """
    scale = (heat_scale or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    if scale != "max":
        return {"ok": True, "enabled": False, "codes": [], "issues": []}

    pen_shots = [
        sh
        for sh in shots
        if isinstance(sh, dict)
        and (
            resolve_sex_arc_beat(sh) == "penetration"
            or (infer_heat_phase(sh) == "act" and _shot_has_penetration_verb(sh))
        )
        # afterglow/bridge may inherit rhythm language — only lint act/entry meat
        and infer_heat_phase(sh) in SEX_PHASES | {"foreplay"}
    ]
    if not pen_shots:
        return {
            "ok": True,
            "enabled": True,
            "codes": [],
            "issues": [],
            "note": "no penetration shots for both-undress check",
        }

    weak_hero: list[str] = []
    weak_partner: list[str] = []
    stated = 0
    for sh in pen_shots:
        sid = str(sh.get("id") or "?")
        hw = resolve_wardrobe_state(sh)
        if hw not in {"undressed", "bare"}:
            weak_hero.append(f"{sid}:{hw or 'none'}")
        # penetration IRON: prefer bare at insert
        if hw == "undressed" and resolve_sex_arc_beat(sh) == "penetration":
            # undressed ok for early act; bare preferred — only fail if partial/full
            pass
        pw = resolve_partner_wardrobe_state(sh)
        if pw is not None:
            stated += 1
            if (WARDROBE_UNDRESS_RANK.get(pw) or 0) < WARDROBE_UNDRESS_RANK["undressed"]:
                weak_partner.append(f"{sid}:{pw}")

    if weak_hero:
        codes.append("SEX_BOTH_UNDRESS_MISSING")
        issues.append(
            {
                "code": "SEX_BOTH_UNDRESS_MISSING",
                "severity": "warning",
                "message": (
                    "penetration shots not undressed/bare for heroine: "
                    + ", ".join(weak_hero[:8])
                    + " — 插入时女方衣裤脱尽（≥undressed，建议 bare）。"
                ),
            }
        )
    if weak_partner:
        codes.append("SEX_BOTH_UNDRESS_MISSING")
        issues.append(
            {
                "code": "SEX_BOTH_UNDRESS_MISSING",
                "severity": "warning",
                "message": (
                    "partner_wardrobe_state too dressed on penetration: "
                    + ", ".join(weak_partner[:8])
                    + " — 男/对方至少下装脱尽（≥undressed）；禁军裤内裤冒充插入。"
                ),
            }
        )
    if stated == 0:
        codes.append("SEX_BOTH_UNDRESS_UNSTATED")
        issues.append(
            {
                "code": "SEX_BOTH_UNDRESS_UNSTATED",
                "severity": "info",
                "message": (
                    "partner_wardrobe_state not set on any penetration shot — "
                    "set partner_wardrobe_state=undressed|bare for 双方脱尽 evidence."
                ),
            }
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "enabled": True,
        "codes": sorted(set(codes)),
        "issues": issues,
        "partner_stated_n": stated,
        "weak_hero": weak_hero,
        "weak_partner": weak_partner,
        "note": "both undress IRON: heroine bare/undressed + partner ≥undressed when stated",
    }


# 色气 6 项 checklist（ecchi-story · Wave 3）
ECCHI_CHECKLIST_ITEMS: tuple[str, ...] = (
    "distance_ladder",  # 身体距离阶梯
    "wardrobe_disorder",  # 服装失序
    "sensory_words",  # 感官词
    "power_gap",  # 权力差
    "double_entendre",  # 双关金句
    "completion_beat",  # 办事完成拍
)
_ECCHI_DISTANCE = ("贴", "跨坐", "耳语", "靠近", "距离", "压近", "贴身", "close", "straddle")
_ECCHI_WARDROBE = ("滑肩", "卸", "半裸", "失序", "扣", "湿", "bare", "undress", "partial", "strap")
_ECCHI_SENSORY = ("热", "潮", "喘", "香", "心跳", "指尖", "腿软", "汗", "湿", "breath", "sweat")
_ECCHI_POWER = ("教", "规矩", "落锁", "加演", "主导", "不许", "命令", "pin", "lock")
_ECCHI_DOUBLE = ("双关", "加练", "续借", "未完", "下回", "换你", "办")
_ECCHI_COMPLETE = ("办穿", "办完", "高潮", "射出", "腿软", "finish", "climax", "arch-finish")


def lint_ecchi_checklist(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    min_items: int | None = None,
) -> dict[str, Any]:
    """色气升级清单：max 须 ≥6 项全占；hot 建议 ≥4。字段+文案启发式，非像素 CV。"""
    scale = (heat_scale or "").strip().lower() or None
    if scale not in {"max", "hot"}:
        return {
            "ok": True,
            "enabled": False,
            "score": 0,
            "items": {},
            "missing": [],
            "codes": [],
            "note": "ecchi checklist skipped (not max/hot)",
        }
    need = int(min_items) if min_items is not None else (6 if scale == "max" else 4)
    blobs: list[str] = []
    wardrobe_states: list[str] = []
    phases: list[str] = []
    for sh in shots:
        if not isinstance(sh, dict):
            continue
        phases.append(infer_heat_phase(sh))
        wardrobe_states.append(str(resolve_wardrobe_state(sh) or ""))
        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
        parts = [
            str(sh.get("nar") or ""),
            str(dsl.get("action") or ""),
            str(dsl.get("subject") or ""),
            str(sh.get("must_show") or ""),
            str(sh.get("title") or ""),
        ]
        blobs.append(" ".join(parts).lower())
    text = " ".join(blobs)
    items = {
        "distance_ladder": any(m in text for m in _ECCHI_DISTANCE)
        or any(p in {"foreplay", "act"} for p in phases),
        "wardrobe_disorder": any(m in text for m in _ECCHI_WARDROBE)
        or any(w in {"partial", "undressed", "bare"} for w in wardrobe_states),
        "sensory_words": any(m in text for m in _ECCHI_SENSORY),
        "power_gap": any(m in text for m in _ECCHI_POWER),
        "double_entendre": any(m in text for m in _ECCHI_DOUBLE),
        "completion_beat": any(m in text for m in _ECCHI_COMPLETE)
        or any(p == "climax" for p in phases),
    }
    present = [k for k, v in items.items() if v]
    missing = [k for k, v in items.items() if not v]
    score = len(present)
    codes: list[str] = []
    issues: list[dict[str, Any]] = []
    if score < need:
        codes.append("ECCHI_CHECKLIST_THIN")
        issues.append(
            {
                "code": "ECCHI_CHECKLIST_THIN",
                "severity": "warning" if scale == "max" else "info",
                "message": (
                    f"色气 checklist {score}/{need} — missing: {', '.join(missing) or 'none'}. "
                    "max 须 6 项全占（距离/失序/感官/权力/双关/完成拍）。"
                ),
            }
        )
    return {
        "ok": score >= need,
        "enabled": True,
        "score": score,
        "need": need,
        "items": items,
        "present": present,
        "missing": missing,
        "codes": codes,
        "issues": issues,
        "note": "ecchi-story 6-item checklist; field+nar heuristic (not pixel CV)",
    }


def suggest_impact_boost_actions(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    heat_rep: dict[str, Any] | None = None,
    impact: dict[str, Any] | None = None,
    target_score: float = 90.0,
) -> dict[str, Any]:
    """Concrete patch list to push erotic impact toward S (≥90)."""
    scale = (heat_scale or "").strip().lower() or "max"
    impact = impact or compute_erotic_impact_score(shots, heat_scale=scale, heat_rep=heat_rep)
    score = float(impact.get("score") or 0.0)
    bands = impact.get("bands") if isinstance(impact.get("bands"), dict) else {}
    actions: list[dict[str, Any]] = []
    if score + 1e-9 >= target_score:
        return {
            "ok": True,
            "needed": False,
            "score": score,
            "target": target_score,
            "actions": [],
            "note": f"impact {score} already ≥ S target {target_score}",
        }

    def _add(kind: str, message: str, **extra: Any) -> None:
        actions.append({"kind": kind, "message": message, **extra})

    if float(bands.get("sex_duration") or 0) < 25:
        _add(
            "lengthen_meat",
            "加长 act/climax duration_sec（目标 sex≥50%，建议≥55%）",
            boost_sec=4.0,
            phases=["act", "climax"],
        )
    if float(bands.get("bare_peak") or 0) < 15:
        _add(
            "set_bare_peak",
            "climax 至少 1 镜 wardrobe_state=bare（能露就露）",
            wardrobe_state="bare",
            phases=["climax"],
        )
    if float(bands.get("detail_cu") or 0) < 15:
        _add(
            "add_detail_cu",
            "肉戏块加 1 镜 coverage_role=detail / close-up insert（定器特写）",
            coverage_role="detail",
            phases=["act"],
        )
    if float(bands.get("sex_arc") or 0) < 20:
        _add(
            "fix_sex_arc",
            "补齐 前戏→插入→射出：sex_arc_beat + penetration/release 动词",
            phases=["foreplay", "act", "climax"],
        )
    if float(bands.get("penetration_verbs") or 0) < 10:
        _add(
            "penetration_verbs",
            "act 镜 dsl.action/nar 写入 hips-sink/thrust/straddle/沉腰",
            phases=["act"],
        )
    if float(bands.get("intimacy") or 0) < 15:
        _add(
            "raise_intimacy",
            "压缩 setup，增加 foreplay+act+climax 镜比（亲密≥60%）",
            phases=["setup"],
        )
    # Always suggest mute-frame human evidence for act/climax when below S
    meat_ids = [
        str(sh.get("id") or "?")
        for sh in shots
        if isinstance(sh, dict) and infer_heat_phase(sh) in SEX_PHASES
    ]
    if meat_ids:
        _add(
            "mute_frame_review",
            "act/climax 人工 mute-frame coitus≥4（像素办事可读，非字段绿）",
            shot_ids=meat_ids[:12],
        )
    return {
        "ok": True,
        "needed": True,
        "score": score,
        "target": target_score,
        "gap": round(target_score - score, 1),
        "bands": bands,
        "actions": actions,
        "note": "apply via aifilm heat boost --apply (field patches only; stills remain agent work)",
    }


def apply_impact_boost_patches(
    shots: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply field-level impact boosts in-place. Returns counts of changes."""
    changed: list[str] = []
    for act in actions:
        kind = str(act.get("kind") or "")
        if kind == "lengthen_meat":
            # H3 native clips are ~5.2s; stretch hard-cap ~5.9 (suse final IRON).
            # Prefer shrinking non-meat elsewhere over inventing unstretchable 9–10s slots.
            boost = float(act.get("boost_sec") or 4.0)
            cap = float(act.get("max_duration_sec") or 5.9)
            for sh in shots:
                if not isinstance(sh, dict):
                    continue
                if infer_heat_phase(sh) in SEX_PHASES:
                    try:
                        d = float(sh.get("duration_sec") or 6.0)
                    except (TypeError, ValueError):
                        d = 6.0
                    new_d = min(cap, round(d + boost, 1))
                    if new_d > d + 1e-9:
                        sh["duration_sec"] = new_d
                        changed.append(f"len:{sh.get('id')}")
                    elif d > cap:
                        sh["duration_sec"] = cap
                        changed.append(f"cap:{sh.get('id')}")
        elif kind == "set_bare_peak":
            for sh in shots:
                if not isinstance(sh, dict):
                    continue
                if infer_heat_phase(sh) == "climax":
                    sh["wardrobe_state"] = "bare"
                    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                    dsl["wardrobe_state"] = "bare"
                    sh["dsl"] = dsl
                    changed.append(f"bare:{sh.get('id')}")
        elif kind == "add_detail_cu":
            # retarget first act shot without detail
            for sh in shots:
                if not isinstance(sh, dict):
                    continue
                if infer_heat_phase(sh) != "act":
                    continue
                cr = str(
                    sh.get("coverage_role") or (sh.get("dsl") or {}).get("coverage_role") or ""
                ).lower()
                if cr == "detail":
                    continue
                sh["coverage_role"] = "detail"
                dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
                cam["shot_size"] = cam.get("shot_size") or "close-up insert"
                dsl["camera"] = cam
                dsl["coverage_role"] = "detail"
                dsl["framing"] = dsl.get("framing") or "union_closeup"
                sh["dsl"] = dsl
                if not sh.get("sex_arc_beat"):
                    sh["sex_arc_beat"] = "penetration"
                changed.append(f"detail:{sh.get('id')}")
                break
        elif kind == "penetration_verbs":
            for sh in shots:
                if not isinstance(sh, dict):
                    continue
                if infer_heat_phase(sh) != "act":
                    continue
                if _shot_has_penetration_verb(sh):
                    continue
                dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                dsl["action"] = (
                    str(dsl.get("action") or "") + " hips-sink thrust-rhythm straddle"
                ).strip()
                dsl["motion"] = (
                    str(dsl.get("motion") or "") + " rhythm_hips hips-sink twice"
                ).strip()
                sh["dsl"] = dsl
                if not resolve_coitus_beat(sh):
                    sh["coitus_beat"] = "rhythm"
                changed.append(f"verb:{sh.get('id')}")
    return {"changed": len(changed), "ids": changed}


def compute_erotic_impact_score(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    heat_rep: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """0–100 adult impact scorecard (duration × undress × arc × CU × verbs)."""
    scale = (heat_scale or "").strip().lower() or "max"
    if not shots:
        return {"score": 0, "bands": {}, "note": "empty"}
    rep = heat_rep
    if rep is None:
        # lightweight local metrics only
        rep = {}
    sex_ratio = float(rep.get("sex_duration_ratio") or 0.0)
    if not sex_ratio:
        total = sum(_shot_duration_sec(sh) for sh in shots if isinstance(sh, dict)) or 1.0
        sex = sum(
            _shot_duration_sec(sh)
            for sh in shots
            if isinstance(sh, dict) and infer_heat_phase(sh) in SEX_PHASES
        )
        sex_ratio = sex / total
    intimacy = float(rep.get("intimacy_ratio") or rep.get("intimacy_duration_ratio") or 0.0)
    bare_ok = (
        bool((rep.get("wardrobe") or {}).get("bare_peak_ok"))
        if rep.get("wardrobe")
        else any(resolve_wardrobe_state(sh) == "bare" for sh in shots if isinstance(sh, dict))
    )
    arc = lint_sex_arc(shots, heat_scale=scale) if scale == "max" else {"ok": True}
    detail = lint_sex_detail_cu(shots, heat_scale=scale)
    pen_n = sum(1 for sh in shots if isinstance(sh, dict) and _shot_has_penetration_verb(sh))
    bands = {
        "sex_duration": min(25.0, sex_ratio / 0.50 * 25.0),
        "intimacy": min(15.0, (intimacy or sex_ratio) / 0.60 * 15.0),
        "bare_peak": 15.0 if bare_ok else 0.0,
        "sex_arc": 20.0 if arc.get("ok") else (10.0 if arc.get("has_penetration") else 0.0),
        "detail_cu": 15.0 if detail.get("detail_shots") else 0.0,
        "penetration_verbs": min(10.0, pen_n * 3.0),
    }
    score = round(sum(bands.values()), 1)
    grade = (
        "S"
        if score >= 90
        else "A"
        if score >= 75
        else "B"
        if score >= 60
        else "C"
        if score >= 40
        else "D"
    )
    return {
        "score": score,
        "grade": grade,
        "bands": {k: round(v, 1) for k, v in bands.items()},
        "sex_duration_ratio": round(sex_ratio, 3),
        "detail_shots": detail.get("detail_shots") or [],
        "sex_arc_ok": bool(arc.get("ok")),
        "bare_peak_ok": bare_ok,
        "note": "erotic impact 0–100; S≥90 A≥75 — max product target A+",
    }


def lint_sex_arc(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Adult max 起承转合: 前戏 → 插入 → 射出 must all exist (P0 · 2026-07-27).

    Codes: SEX_ARC_FOREPLAY_MISSING · SEX_ARC_PENETRATION_MISSING ·
    SEX_ARC_CLIMAX_RELEASE_MISSING · SEX_ARC_HUG_AS_SEX · SEX_ARC_ORDER_BROKEN ·
    SEX_ARC_PENETRATION_VERB_WEAK · SEX_ARC_RELEASE_MARKER_WEAK · SEX_ARC_RATIO_SKEW
    """
    scale = (heat_scale or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale != "max":
        return {
            "ok": True,
            "enabled": False,
            "codes": [],
            "issues": [],
            "beats_present": {},
            "note": "sex arc lint skipped (not heat_scale=max)",
        }

    # Eligible when film has intimacy core
    phases = [infer_heat_phase(sh) for sh in shots if isinstance(sh, dict)]
    if not any(p in SEX_PHASES or p == "foreplay" for p in phases):
        return {
            "ok": True,
            "enabled": True,
            "codes": [],
            "issues": [],
            "beats_present": {},
            "note": "sex arc skipped (no foreplay/act/climax)",
        }

    beats_present: dict[str, list[str]] = {b: [] for b in SEX_ARC_BEATS}
    order: list[tuple[int, str, str]] = []  # index, beat, id
    hug_only: list[str] = []
    beat_dur: dict[str, float] = {b: 0.0 for b in SEX_ARC_BEATS}
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or f"idx{i}")
        beat = resolve_sex_arc_beat(shot)
        if beat:
            beats_present.setdefault(beat, []).append(sid)
            order.append((i, beat, sid))
            beat_dur[beat] = beat_dur.get(beat, 0.0) + _shot_duration_sec(shot)
        ph = infer_heat_phase(shot)
        if ph in SEX_PHASES and shot_coitus_pseudo_only(shot):
            hug_only.append(sid)

    has_foreplay = bool(beats_present.get("foreplay")) or any(
        infer_heat_phase(sh) == "foreplay" for sh in shots if isinstance(sh, dict)
    )
    # penetration requires verb/coitus-readable — not bare hug
    has_penetration = bool(beats_present.get("penetration"))
    if not has_penetration:
        for sh in shots:
            if not isinstance(sh, dict):
                continue
            if infer_heat_phase(sh) == "act" and _shot_has_penetration_verb(sh):
                has_penetration = True
                beats_present.setdefault("penetration", []).append(str(sh.get("id") or "?"))
                beat_dur["penetration"] = beat_dur.get("penetration", 0.0) + _shot_duration_sec(sh)
                break

    # climax phase alone is NOT enough — need release markers
    has_release = bool(beats_present.get("climax_release"))
    if not has_release:
        for sh in shots:
            if not isinstance(sh, dict):
                continue
            if infer_heat_phase(sh) == "climax" and _shot_has_release_marker(sh):
                has_release = True
                beats_present.setdefault("climax_release", []).append(str(sh.get("id") or "?"))
                beat_dur["climax_release"] = beat_dur.get(
                    "climax_release", 0.0
                ) + _shot_duration_sec(sh)
                break

    # Weak verb diagnostics on act block
    act_shots = [sh for sh in shots if isinstance(sh, dict) and infer_heat_phase(sh) == "act"]
    if act_shots and has_penetration is False:
        if any(resolve_wardrobe_state(sh) in {"undressed", "bare"} for sh in act_shots):
            _issue(
                "SEX_ARC_PENETRATION_VERB_WEAK",
                "warning",
                "act is undressed/bare but lacks penetration verbs "
                "(hips-sink/thrust/straddle/union) — 裸抱不算插入。",
            )
    climax_shots = [sh for sh in shots if isinstance(sh, dict) and infer_heat_phase(sh) == "climax"]
    if climax_shots and not has_release:
        _issue(
            "SEX_ARC_RELEASE_MARKER_WEAK",
            "warning",
            "climax phase present but no release markers "
            "(arch-finish/高潮/射出) — 合拍须可读为高潮射出。",
        )

    if not has_foreplay:
        _issue(
            "SEX_ARC_FOREPLAY_MISSING",
            "warning",
            "sex arc 起 missing: no foreplay beat — add heat_phase=foreplay or "
            "sex_arc_beat=foreplay / undress contact before penetration. "
            "See lessons-2026-07-27-adult-scale-max-sex-arc.md",
        )
    if not has_penetration:
        _issue(
            "SEX_ARC_PENETRATION_MISSING",
            "warning",
            "sex arc 转 missing: no penetration/insert beat — act must show "
            "纳入/抽送 (hips-sink/thrust/straddle/union), not hug-only. "
            "set sex_arc_beat=penetration or coitus_beat=union|rhythm.",
        )
    if not has_release:
        _issue(
            "SEX_ARC_CLIMAX_RELEASE_MISSING",
            "warning",
            "sex arc 合 missing: no climax_release / 射出高潮 beat — climax must "
            "read as peak release (arch-finish/高潮/射出). set heat_phase=climax "
            "and sex_arc_beat=climax_release.",
        )
    if hug_only and not has_penetration:
        _issue(
            "SEX_ARC_HUG_AS_SEX",
            "warning",
            f"act/climax uses hug/kiss-only language: {','.join(hug_only[:8])} — "
            "not coitus; rewrite with penetration verbs.",
        )

    # Order: first foreplay index should be before first penetration before first release
    def _first(beat: str) -> int | None:
        for i, b, _sid in order:
            if b == beat:
                return i
        for i, sh in enumerate(shots):
            if not isinstance(sh, dict):
                continue
            if beat == "foreplay" and infer_heat_phase(sh) == "foreplay":
                return i
            if (
                beat == "penetration"
                and infer_heat_phase(sh) == "act"
                and _shot_has_penetration_verb(sh)
            ):
                return i
            if (
                beat == "climax_release"
                and infer_heat_phase(sh) == "climax"
                and _shot_has_release_marker(sh)
            ):
                return i
        return None

    i_fp, i_pen, i_rel = _first("foreplay"), _first("penetration"), _first("climax_release")
    if (
        i_fp is not None
        and i_pen is not None
        and i_rel is not None
        and not (i_fp <= i_pen <= i_rel)
    ):
        _issue(
            "SEX_ARC_ORDER_BROKEN",
            "warning",
            f"sex arc order broken (foreplay@{i_fp}, penetration@{i_pen}, "
            f"release@{i_rel}) — 起→转→合 must progress in time order.",
        )

    # Duration skew: penetration / release share of meat window (hard on max · 2026-07-29)
    meat_sec = sum(
        _shot_duration_sec(sh)
        for sh in shots
        if isinstance(sh, dict) and infer_heat_phase(sh) in SEX_PHASES | {"foreplay"}
    )
    pen_sec = beat_dur.get("penetration", 0.0)
    rel_sec = beat_dur.get("climax_release", 0.0)
    if meat_sec > 0 and has_penetration and (pen_sec / meat_sec) < 0.25:
        _issue(
            "SEX_ARC_RATIO_SKEW",
            "warning",
            f"penetration duration share {pen_sec / meat_sec:.0%} < 25% of meat window — "
            "加长抽送镜 (转拍建议 ≥35%；hard floor 25%)。",
        )
    if meat_sec > 0 and has_release and (rel_sec / meat_sec) < 0.12:
        _issue(
            "SEX_ARC_RELEASE_RATIO_LOW",
            "warning",
            f"climax_release duration share {rel_sec / meat_sec:.0%} < 12% of meat window — "
            "加长射出/高潮拍 (合拍建议 ≥20%)。",
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "enabled": True,
        "codes": sorted(set(codes)),
        "issues": issues,
        "beats_present": {k: v for k, v in beats_present.items() if v},
        "beat_duration_sec": {k: round(v, 2) for k, v in beat_dur.items() if v > 0},
        "penetration_duration_ratio": round(pen_sec / meat_sec, 3) if meat_sec else None,
        "meat_duration_sec": round(meat_sec, 2),
        "required": list(SEX_ARC_REQUIRED),
        "has_foreplay": has_foreplay,
        "has_penetration": has_penetration,
        "has_climax_release": has_release,
        "note": (
            "sex arc IRON: 前戏→插入→射出 (lessons-2026-07-27-adult-scale-max-sex-arc); "
            "verbs required for penetration; write-spec hard via sex_arc_strict on max"
        ),
    }


def _shot_size_rank(shot: dict[str, Any]) -> int | None:
    """Map shot_size text → L0–L4 rank (higher = tighter)."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    raw = (
        str(
            cam.get("shot_size")
            or dsl.get("shot_size")
            or shot.get("shot_size")
            or shot.get("shotSize")
            or ""
        )
        .strip()
        .lower()
    )
    if not raw:
        return None
    if any(x in raw for x in ("ecu", "extreme close", "insert", "detail", "物件", "局部")):
        return 4
    if any(x in raw for x in ("close-up", "close up", "closeup", "cu", "近景", "特写")):
        return 3
    if any(x in raw for x in ("medium full", "medium-full", "中全", "knee", "3/4")):
        return 1
    if any(x in raw for x in ("wide", "long shot", "establishing", "全景", "大全")):
        return 0
    if any(x in raw for x in ("medium", "中景", "waist")):
        return 2
    return 2  # default medium


def lint_size_ladder(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
) -> dict[str, Any]:
    """Size ladder escalation for adult shorts (WS→MS→CU→ECU pressure)."""
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"}:
        return {
            "ok": True,
            "codes": [],
            "issues": [],
            "note": "size ladder skipped (not max/hot)",
        }

    hardcore = profile in {"hardcore_male", "hardcore", "重口男向"}
    sev = "warning"
    n = len([s for s in shots if isinstance(s, dict)])
    ranks: list[tuple[str, int | None, str]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "")
        r = _shot_size_rank(shot)
        ph = infer_heat_phase(shot)
        ranks.append((sid, r, ph))

    # max IRON 2026-07-28: size pressure is warning (write-spec size_ladder_strict);
    # soft hot remains info-only unless hardcore
    ladder_sev = sev if (hardcore or scale == "max") else "info"

    # Flat triple: 3 consecutive same explicit rank
    for i in range(len(ranks) - 2):
        a, b, c = ranks[i][1], ranks[i + 1][1], ranks[i + 2][1]
        if a is not None and a == b == c and n >= 6:
            _issue(
                "SIZE_STACK_FLAT",
                ladder_sev,
                f"three consecutive same shot_size rank L{a} "
                f"({ranks[i][0]},{ranks[i + 1][0]},{ranks[i + 2][0]}) — "
                "vary size ladder (WS→MS→CU→insert).",
            )
            break

    # Quotas for adult 8–12 spine (hardcore warnings; max info)
    if n >= 6:
        present = [r for _, r, _ in ranks if r is not None]
        if present:
            has_wide = any(r <= 1 for r in present)
            has_med = sum(1 for r in present if r == 2)
            has_cu = sum(1 for r in present if r == 3)
            has_l4 = sum(1 for r in present if r >= 4)
            if not has_wide:
                _issue(
                    "SIZE_LADDER_NO_WIDE",
                    ladder_sev,
                    "adult size ladder needs ≥1 wide/medium-full (L0/L1) establishing shot",
                )
            if has_med < 1 and hardcore:
                _issue(
                    "SIZE_LADDER_NO_MEDIUM",
                    ladder_sev,
                    "hardcore: need medium (L2) body-relation shots",
                )
            if has_cu < 1:
                _issue(
                    "SIZE_LADDER_NO_CU",
                    ladder_sev,
                    "adult size ladder needs ≥1 close-up (L3) reaction/pressure",
                )
            if (hardcore or scale == "max") and has_l4 < 1:
                _issue(
                    "SIZE_LADDER_NO_INSERT",
                    ladder_sev,
                    "max/hardcore: need ≥1 L4 insert (hand/hip/fabric/定器 detail)",
                )

    # act→climax: peak tightness should not suddenly open to wide
    act_ranks = [r for _, r, ph in ranks if ph in SEX_PHASES and r is not None]
    if len(act_ranks) >= 2:
        for i in range(1, len(act_ranks)):
            if act_ranks[i] <= act_ranks[i - 1] - 2:
                _issue(
                    "SIZE_LADDER_ACT_REOPEN",
                    ladder_sev,
                    "act→climax size suddenly reopens wider — keep pressure (no jump back to wide during sex)",
                )
                break

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "issues": issues,
        "ranks": [{"id": sid, "rank": r, "heat_phase": ph} for sid, r, ph in ranks],
        "note": "size ladder: lessons-2026-07-21-size-ladder-hardcore-stack.md",
    }


def lint_vo_motion_align(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
) -> dict[str, Any]:
    """nar sex verbs should echo dsl.action/motion (声画同动词)."""
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    mismatch: list[str] = []

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"}:
        return {
            "ok": True,
            "codes": [],
            "issues": [],
            "mismatch_shots": [],
            "note": "vo-motion align skipped",
        }

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        ph = infer_heat_phase(shot)
        if ph not in SEX_PHASES:
            continue
        nar = str(shot.get("nar") or "")
        if not nar_has_sex_verb(nar):
            continue
        blob = _shot_visual_pose_blob(shot)
        # at least one sex verb marker from nar should appear in visual blob
        nar_l = nar.lower()
        hits = [m for m in _NAR_SEX_VERB_MARKERS if m.lower() in nar_l]
        if not hits:
            continue
        if not any(h.lower() in blob for h in hits):
            # also accept coitus English markers in visual when Chinese in nar
            if shot_coitus_readable(shot) and nar_has_extreme_spice(nar):
                continue
            mismatch.append(str(shot.get("id") or "?"))

    if mismatch:
        sev = "warning" if profile in {"hardcore_male", "hardcore", "重口男向"} else "info"
        _issue(
            "HEAT_VO_MOTION_MISMATCH",
            sev,
            f"act/climax VO sex verbs not mirrored in dsl.action/motion: "
            f"{', '.join(mismatch[:8])} — 声画同动词（沉腰= hips-sink）。",
        )
    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "issues": issues,
        "mismatch_shots": mismatch,
        "note": "vo-motion alignment for coitus beats",
    }


def lint_sex_pose_variety(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
) -> dict[str, Any]:
    """≥3 act shots should not share identical pose language (防姿势日历)."""
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"}:
        return {"ok": True, "codes": [], "issues": [], "poses": [], "unique": 0}

    act_poses: list[str] = []
    act_ids: list[str] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        if infer_heat_phase(shot) not in SEX_PHASES:
            continue
        pose = resolve_sex_pose(shot) or ""
        if not pose:
            # fingerprint action
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            pose = str(dsl.get("action") or "")[:40].lower()
        act_poses.append(pose)
        act_ids.append(str(shot.get("id") or ""))

    unique = len(set(p for p in act_poses if p))
    if len(act_poses) >= 3 and unique < 2:
        sev = "warning" if profile in {"hardcore_male", "hardcore", "重口男向"} else "info"
        _issue(
            "SEX_POSE_STALE",
            sev,
            f"act/climax poses stale ({unique} unique / {len(act_poses)} shots) — "
            "rotate sex_pose (straddle/cowgirl/from_behind/missionary_pin…).",
        )
    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "issues": issues,
        "poses": act_poses,
        "unique": unique,
        "act_count": len(act_poses),
        "note": "multi-pose variety for act stack",
    }


def lint_montage_craft(
    crafts: list[str] | None,
    *,
    heat_scale: str | None = None,
    audience_profile: str | None = None,
    shot_count: int = 0,
) -> dict[str, Any]:
    """Hardcore adult cuts need craft variety (insert/smash/montage)."""
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    craft_list = [str(c).strip().lower() for c in (crafts or []) if str(c).strip()]
    unique = sorted(set(craft_list))

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"} or shot_count < 6:
        return {
            "ok": True,
            "codes": [],
            "issues": [],
            "unique_crafts": unique,
            "note": "montage lint skipped",
        }

    hardcore = profile in {"hardcore_male", "hardcore", "重口男向"}
    sev = "warning" if hardcore else "info"
    need_kinds = 4 if hardcore else 3
    if craft_list and len(unique) < need_kinds:
        _issue(
            "MONTAGE_FLAT",
            sev,
            f"edit_craft only {len(unique)} kinds {unique[:6]} — need ≥{need_kinds} "
            "(insert_cut/smash_cut/montage_jump…). See montage-hardcore-male.",
        )
    has_insert = any("insert" in c for c in craft_list)
    has_smash = any("smash" in c for c in craft_list)
    if hardcore and craft_list and not has_insert:
        _issue(
            "MONTAGE_NO_INSERT",
            sev,
            "hardcore: need ≥1 insert_cut in edit_craft spine",
        )
    if hardcore and craft_list and not has_smash:
        _issue(
            "MONTAGE_NO_SMASH",
            sev,
            "hardcore: need ≥1 smash_cut in edit_craft spine",
        )
    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "issues": issues,
        "unique_crafts": unique,
        "craft_count": len(craft_list),
        "has_insert": has_insert,
        "has_smash": has_smash,
        "note": "montage craft variety for adult cuts",
    }


def apply_vo_spice_auto(
    shots: list[dict[str, Any]],
    *,
    spice_level: str | None = "extreme",
    max_chars: int = 55,
) -> dict[str, Any]:
    """Reinforce weak adult nar in-place. User substantive lines: append only.

    Returns {fixed: n, ids: [...]} for write-spec notes.
    """
    fixed_ids: list[str] = []
    for sh in shots:
        if not isinstance(sh, dict):
            continue
        ph = infer_heat_phase(sh)
        cb = resolve_coitus_beat(sh)
        nar = str(sh.get("nar") or "").strip()
        spice = nar_has_spice(nar) if nar else False
        sex_v = nar_has_sex_verb(nar) if nar else False
        extreme = nar_has_extreme_spice(nar) if nar else False
        level = (spice_level or "extreme").strip().lower()
        needs = (
            not nar
            or not spice
            or (ph in SEX_PHASES and not sex_v)
            or (level == "extreme" and ph in SEX_PHASES and not extreme)
        )
        if not needs:
            continue
        seeds = suggest_vo_lines(heat_phase=ph, coitus_beat=cb, spice_level=level)
        seed = (seeds[0] if seeds else "沉腰吃进。锁住。").strip()
        # Substantive user line: append seed rather than replace
        user_substantive = bool(nar) and len(nar) >= 6 and spice
        append_seed = (
            user_substantive
            and ph in SEX_PHASES
            and (not sex_v or (level == "extreme" and not extreme))
        )
        merged = f"{nar.rstrip('。.!！')}。{seed}" if append_seed else seed
        sh["nar"] = merged[:max_chars]
        sid = str(sh.get("id") or "?")
        fixed_ids.append(sid)
    return {"fixed": len(fixed_ids), "ids": fixed_ids}


def suggest_vo_lines(
    *,
    heat_phase: str | None = None,
    coitus_beat: str | None = None,
    spice_level: str | None = "explicit",
) -> list[str]:
    """Strong adult nar seeds by phase/beat (agent / heat vo-suggest)."""
    ph = (heat_phase or "act").strip().lower()
    cb = (coitus_beat or "").strip().lower()
    extreme = (spice_level or "").strip().lower() == "extreme"
    bank: dict[str, list[str]] = {
        "setup": [
            "展厅落锁。今晚只加演你一场。",
            "门一闩。规矩作废，只办你。",
        ],
        "foreplay": [
            "肩带一滑。卸甲半裸，规矩失效。",
            "扣子崩开。她把你按进失序。",
        ],
        "act": [
            "沉腰吃进。再顶，磨到发软。",
            "跨坐落稳。整根吞满，锁住。",
            "再沉腰。节奏是她给的，办穿前奏。",
        ],
        "climax": [
            "失声办穿。背一弓，腿软。",
            "她高潮失声。余颤还在夹。",
        ],
        "afterglow": [
            "贴耳：下一场——换你顶。",
            "未完。她咬耳：换你来办。",
        ],
    }
    if extreme:
        bank["act"] = [
            "沉腰吃进整根。再顶深，磨到发软。",
            "跨坐吞满。肏穿前的节奏是她给的。",
            "再插深。锁腰夹紧，不许退。",
            "腰猛撞。体内烧，穿透到底。",
        ]
        bank["climax"] = [
            "失声办穿。灌满前背一弓，腿软。",
            "高潮绞紧。余颤喷在你身上。",
            "体内炸裂。全部射在你里面。",
            "creampie溢出。身体止不住地漏。",
        ]
    by_cb = {
        "entry": bank["setup"],
        "undress": bank["foreplay"],
        "union": ["跨坐落稳。整根吃进，锁住。", "髋贴髋。结合瞬间，不许退。"],
        "rhythm": bank["act"],
        "deep_thrust": [
            "深插到底。腰猛撞，不退。",
            "穿透她。体内顶，节奏她收。",
            "抽送到底。骨盆撞一起，停不下。",
        ]
        if extreme
        else ["深插。节奏稳住，不退。"],
        "lock": [
            "腿锁腰。攥床单，再夹紧。",
            "锁死。指节攥白，不许拔。",
        ],
        "internal_peak": [
            "体内炸裂。全部射在你里面。",
            "高潮绞紧。余颤喷在你身上。",
            "内射完成。她止不住地颤抖。",
        ]
        if extreme
        else ["体内释放。高潮。颤抖。"],
        "creampie_release": [
            "creampie溢出。身体止不住地漏。",
            "汁液溢出。体内炸裂。",
            "她漏得停不下来。浸透。",
        ]
        if extreme
        else ["内部释放。湿润。颤。"],
        "finish": bank["climax"],
        "hook": bank["afterglow"],
    }
    if cb in by_cb:
        return list(by_cb[cb])
    return list(bank.get(ph, bank["act"]))


def _merge_sub_issues(rep: dict[str, Any], issues: list[dict[str, Any]], codes: list[str]) -> None:
    """Merge a sub-lint report's issues into the parent issues/codes lists."""
    for iss in rep.get("issues") or []:
        if not isinstance(iss, dict):
            continue
        c = str(iss.get("code") or "")
        if c and c not in codes:
            codes.append(c)
        issues.append(iss)


def lint_heat_arc(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
    intimacy_min_ratio: float | None = None,
    setup_max_ratio: float | None = None,
    sex_min_duration_ratio: float | None = None,
    audience_profile: str | None = None,
    advise: bool = False,
    coitus_grammar: dict[str, Any] | None = None,
    spice_level: str | None = None,
    edit_craft: list[str] | None = None,
    source_excerpt: str | None = None,
) -> dict[str, Any]:
    """Heat metrics + sex-duration floor for adult films (max IRON 2026-07-24).

    - intimacy_ratio / setup_ratio: **shot-count** share
    - sex_duration_ratio / intimacy_duration_ratio: **duration_sec-weighted**
      sex = act+climax only (性爱片段); intimacy = foreplay+act+climax
    - heat_scale=max: sex_duration_ratio < floor (default **50%**) → HEAT_SEX_DURATION_LOW
      (write-spec hard by default via sex_floor_strict)
    - intimacy < 70% / setup > 20% → HEAT_INTIMACY_RATIO_LOW / HEAT_SETUP_RATIO_HIGH
      (write-spec hard via heat_arc_strict default true on max)
    - coitus grammar + size ladder (strict via film_spec flags)
    """
    scale = (heat_scale or "").strip().lower() or None
    profile = (audience_profile or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    n = len(shots) or 0
    phases: dict[str, int] = {p: 0 for p in HEAT_PHASES}
    phase_dur: dict[str, float] = {p: 0.0 for p in HEAT_PHASES}
    phase_by_shot: list[dict[str, Any]] = []
    total_dur = 0.0
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        ph = infer_heat_phase(shot)
        dur = _shot_duration_sec(shot)
        phases[ph] = phases.get(ph, 0) + 1
        phase_dur[ph] = phase_dur.get(ph, 0.0) + dur
        total_dur += dur
        phase_by_shot.append(
            {
                "id": str(shot.get("id") or ""),
                "heat_phase": ph,
                "duration_sec": round(dur, 3),
                "coitus_beat": resolve_coitus_beat(shot),
            }
        )

    intimacy_n = sum(phases.get(p, 0) for p in INTIMACY_PHASES)
    setup_n = phases.get("setup", 0)
    climax_n = phases.get("climax", 0)
    act_n = phases.get("act", 0)
    foreplay_n = phases.get("foreplay", 0)
    sex_n = act_n + climax_n
    intimacy_ratio = (intimacy_n / n) if n else 0.0
    setup_ratio = (setup_n / n) if n else 0.0
    sex_shot_ratio = (sex_n / n) if n else 0.0

    intimacy_dur = sum(phase_dur.get(p, 0.0) for p in INTIMACY_PHASES)
    setup_dur = phase_dur.get("setup", 0.0)
    sex_dur = sum(phase_dur.get(p, 0.0) for p in SEX_PHASES)
    intimacy_duration_ratio = (intimacy_dur / total_dur) if total_dur > 0 else 0.0
    setup_duration_ratio = (setup_dur / total_dur) if total_dur > 0 else 0.0
    sex_duration_ratio = (sex_dur / total_dur) if total_dur > 0 else 0.0

    # Author override for advisory / floor targets
    guide_int = (
        float(intimacy_min_ratio) if intimacy_min_ratio is not None else ADVISORY_MAX_INTIMACY_RATIO
    )
    guide_setup = (
        float(setup_max_ratio) if setup_max_ratio is not None else ADVISORY_MAX_SETUP_RATIO
    )
    if sex_min_duration_ratio is not None:
        sex_floor = float(sex_min_duration_ratio)
    elif profile in {"hardcore_male", "hardcore", "重口男向"}:
        sex_floor = HARDCORE_SEX_DURATION_TARGET
    else:
        sex_floor = DEFAULT_SEX_DURATION_FLOOR
    guide_sex = (
        HARDCORE_SEX_DURATION_TARGET
        if profile in {"hardcore_male", "hardcore", "重口男向"}
        else ADVISORY_MAX_SEX_DURATION_RATIO
    )

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    # Product floor: act+climax duration share (性爱片段) for max / hot
    # Min sample: ≥4 shots or ≥24s plate so tiny tests do not false-trigger
    sex_gate_eligible = n >= 4 or total_dur + 1e-9 >= 24.0
    if scale == "max" and sex_gate_eligible:
        if sex_dur <= 0:
            _issue(
                "HEAT_SEX_DURATION_LOW",
                "warning",
                "heat_scale=max but act+climax duration is 0s — "
                f"性爱片段 must be ≥{sex_floor:.0%} of total plate duration "
                f"(need ≥{sex_floor * total_dur:.1f}s act+climax). "
                "Add heat_phase=act/climax shots or raise their duration_sec.",
            )
        elif sex_duration_ratio + 1e-9 < sex_floor:
            need_sec = sex_floor * total_dur
            _issue(
                "HEAT_SEX_DURATION_LOW",
                "warning",
                f"性爱片段(act+climax) duration {sex_dur:.1f}s / {total_dur:.1f}s "
                f"= {sex_duration_ratio:.0%} < floor {sex_floor:.0%} "
                f"(need ≥{need_sec:.1f}s). Replan spine: more/longer act+climax plates. "
                "Override: sex_min_duration_ratio or sex_floor_strict:false.",
            )
    elif scale == "hot" and sex_gate_eligible:
        hot_floor = (
            float(sex_min_duration_ratio)
            if sex_min_duration_ratio is not None
            else HOT_SEX_DURATION_FLOOR
        )
        if sex_duration_ratio + 1e-9 < hot_floor:
            _issue(
                "HEAT_SEX_DURATION_LOW",
                "warning",
                f"hot: sex duration {sex_duration_ratio:.0%} < soft floor {hot_floor:.0%} "
                f"({sex_dur:.1f}s/{total_dur:.1f}s act+climax)",
            )

    # max IRON: intimacy / setup are hard-relevant warnings (heat_arc_strict)
    if scale == "max" and n >= 6:
        if act_n + climax_n == 0:
            _issue(
                "HEAT_ACT_CLIMAX_EMPTY",
                "warning",
                "heat_scale=max but no act/climax phase inferred — "
                "add 进行/高潮完成 beats if that matches the brief",
            )
        elif intimacy_ratio + 1e-9 < EXTREME_INTIMACY_FLOOR:
            _issue(
                "HEAT_INTIMACY_RATIO_LOW",
                "warning",
                f"max IRON: intimacy core {intimacy_ratio:.0%} < floor "
                f"{EXTREME_INTIMACY_FLOOR:.0%} (foreplay+act+climax shot share). "
                "Cut setup; add body beats. Override: heat_arc_strict:false.",
            )
        if setup_ratio > EXTREME_SETUP_CEILING + 1e-9:
            _issue(
                "HEAT_SETUP_RATIO_HIGH",
                "warning",
                f"max IRON: setup phase {setup_ratio:.0%} > ceiling "
                f"{EXTREME_SETUP_CEILING:.0%} — enter undress/act earlier. "
                "Override: heat_arc_strict:false.",
            )

    # Optional full advisory (agent asked heat_arc_advise / guide ratios)
    if advise and scale in {"max", "hot"} and n >= 6:
        if intimacy_ratio + 1e-9 < guide_int:
            _issue(
                "HEAT_ADVISORY_INTIMACY",
                "info",
                f"advisory: intimacy core {intimacy_ratio:.0%} < guide {guide_int:.0%} "
                f"(shot-count; not a gate unless heat_arc_strict)",
            )
        if setup_ratio > guide_setup + 1e-9:
            _issue(
                "HEAT_ADVISORY_SETUP",
                "info",
                f"advisory: setup {setup_ratio:.0%} > guide {guide_setup:.0%}",
            )
        if climax_n < 1 and scale == "max":
            _issue(
                "HEAT_ADVISORY_CLIMAX",
                "info",
                "advisory: no climax phase — add completion beat if brief wants 办事完成",
            )
        if sex_duration_ratio + 1e-9 < guide_sex:
            _issue(
                "HEAT_ADVISORY_SEX_DURATION",
                "info",
                f"advisory: sex duration {sex_duration_ratio:.0%} < guide {guide_sex:.0%} "
                f"({sex_dur:.1f}s/{total_dur:.1f}s); hard floor is {sex_floor:.0%} for max",
            )

    # Undress ladder: act/climax cannot stay full armor/dress
    wardrobe_rep = lint_sex_wardrobe(
        shots,
        heat_scale=scale,
        audience_profile=profile,
    )
    _merge_sub_issues(wardrobe_rep, issues, codes)

    # Continuous challenge max scale — 持续挑战尺度最大 (no cool-down / stall)
    esc_rep = lint_heat_escalation_challenge(shots, heat_scale=scale)
    _merge_sub_issues(esc_rep, issues, codes)

    # VO 荤梗：实打实办事剧，旁白不能纯文艺
    level = normalize_spice_level(spice_level, heat_scale=scale, audience_profile=profile)
    vo_rep = lint_sex_vo_spice(
        shots,
        heat_scale=scale,
        audience_profile=profile,
        spice_level=level,
    )
    _merge_sub_issues(vo_rep, issues, codes)

    # User source fidelity: ban wholesale 展厅-template overwrite of user script
    fidelity_rep = lint_user_source_fidelity(
        shots,
        heat_scale=scale,
        source_excerpt=source_excerpt,
    )
    _merge_sub_issues(fidelity_rep, issues, codes)

    # Coitus grammar + size ladder (impact / pressure)
    coitus_rep = lint_coitus_grammar(
        shots,
        heat_scale=scale,
        audience_profile=profile,
        coitus_grammar=coitus_grammar,
    )
    _merge_sub_issues(coitus_rep, issues, codes)

    # 起承转合 full arc (foreplay → penetration → climax_release)
    sex_arc_rep = lint_sex_arc(shots, heat_scale=scale)
    _merge_sub_issues(sex_arc_rep, issues, codes)

    detail_cu_rep = lint_sex_detail_cu(shots, heat_scale=scale)
    _merge_sub_issues(detail_cu_rep, issues, codes)

    both_undress_rep = lint_both_undress(shots, heat_scale=scale)
    _merge_sub_issues(both_undress_rep, issues, codes)

    size_rep = lint_size_ladder(
        shots,
        heat_scale=scale,
        audience_profile=profile,
    )
    _merge_sub_issues(size_rep, issues, codes)

    vo_motion_rep = lint_vo_motion_align(shots, heat_scale=scale, audience_profile=profile)
    _merge_sub_issues(vo_motion_rep, issues, codes)

    pose_rep = lint_sex_pose_variety(shots, heat_scale=scale, audience_profile=profile)
    _merge_sub_issues(pose_rep, issues, codes)

    montage_rep = lint_montage_craft(
        edit_craft,
        heat_scale=scale,
        audience_profile=profile,
        shot_count=n,
    )
    _merge_sub_issues(montage_rep, issues, codes)

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "warning_count": warn_n,
        "info_count": sum(1 for i in issues if i.get("severity") == "info"),
        "issues": issues,
        "heat_scale": scale,
        "audience_profile": profile,
        "shot_count": n,
        "phase_counts": phases,
        "phase_duration_sec": {k: round(v, 3) for k, v in phase_dur.items()},
        "total_duration_sec": round(total_dur, 3),
        "intimacy_ratio": round(intimacy_ratio, 3),
        "setup_ratio": round(setup_ratio, 3),
        "sex_shot_ratio": round(sex_shot_ratio, 3),
        "intimacy_duration_ratio": round(intimacy_duration_ratio, 3),
        "setup_duration_ratio": round(setup_duration_ratio, 3),
        "sex_duration_ratio": round(sex_duration_ratio, 3),
        "sex_duration_sec": round(sex_dur, 3),
        "intimacy_duration_sec": round(intimacy_dur, 3),
        "sex_duration_floor": sex_floor if scale in {"max", "hot"} else None,
        "act_n": act_n,
        "climax_n": climax_n,
        "foreplay_n": foreplay_n,
        "advisory_intimacy_ratio": guide_int if scale in {"max", "hot"} else None,
        "advisory_setup_ratio": guide_setup if scale in {"max", "hot"} else None,
        "advisory_sex_duration_ratio": guide_sex if scale in {"max", "hot"} else None,
        "phase_by_shot": phase_by_shot,
        "wardrobe": {
            "ok": wardrobe_rep.get("ok"),
            "codes": wardrobe_rep.get("codes"),
            "undress_beats": wardrobe_rep.get("undress_beats"),
            "dressed_sex_shots": wardrobe_rep.get("dressed_sex_shots"),
            "re_dress_shots": wardrobe_rep.get("re_dress_shots"),
            "text_conflict_shots": wardrobe_rep.get("text_conflict_shots"),
            "peak_state": wardrobe_rep.get("peak_state"),
            "bare_peak_ok": wardrobe_rep.get("bare_peak_ok"),
            "per_shot": wardrobe_rep.get("per_shot"),
            "required_states": wardrobe_rep.get("required_states"),
        },
        "escalation_challenge": {
            "ok": esc_rep.get("ok"),
            "codes": esc_rep.get("codes"),
            "peak_rank": esc_rep.get("peak_rank"),
            "climax_seen": esc_rep.get("climax_seen"),
            "regression_shots": esc_rep.get("regression_shots"),
            "stall_shots": esc_rep.get("stall_shots"),
        },
        "spice_level": level,
        "vo_spice": {
            "ok": vo_rep.get("ok"),
            "codes": vo_rep.get("codes"),
            "spice_ratio": vo_rep.get("spice_ratio"),
            "extreme_ratio": vo_rep.get("extreme_ratio"),
            "bland_shots": vo_rep.get("bland_shots"),
            "weak_sex_vo_shots": vo_rep.get("weak_sex_vo_shots"),
            "too_mild_shots": vo_rep.get("too_mild_shots"),
            "per_shot": vo_rep.get("per_shot"),
        },
        "user_source_fidelity": {
            "ok": fidelity_rep.get("ok"),
            "codes": fidelity_rep.get("codes"),
            "pollution_ratio": fidelity_rep.get("pollution_ratio"),
            "polluted_shots": fidelity_rep.get("polluted_shots"),
        },
        "vo_motion": {
            "ok": vo_motion_rep.get("ok"),
            "codes": vo_motion_rep.get("codes"),
            "mismatch_shots": vo_motion_rep.get("mismatch_shots"),
        },
        "poses": {
            "ok": pose_rep.get("ok"),
            "codes": pose_rep.get("codes"),
            "unique": pose_rep.get("unique"),
            "act_count": pose_rep.get("act_count"),
        },
        "montage": {
            "ok": montage_rep.get("ok"),
            "codes": montage_rep.get("codes"),
            "unique_crafts": montage_rep.get("unique_crafts"),
            "has_insert": montage_rep.get("has_insert"),
            "has_smash": montage_rep.get("has_smash"),
        },
        "coitus": {
            "ok": coitus_rep.get("ok"),
            "enabled": coitus_rep.get("enabled"),
            "codes": coitus_rep.get("codes"),
            "beats_covered": coitus_rep.get("beats_covered"),
            "missing_beats": coitus_rep.get("missing_beats"),
            "readable_act_ratio": coitus_rep.get("readable_act_ratio"),
            "unreadable_shots": coitus_rep.get("unreadable_shots"),
        },
        "sex_arc": {
            "ok": sex_arc_rep.get("ok"),
            "codes": sex_arc_rep.get("codes"),
            "beats_present": sex_arc_rep.get("beats_present"),
            "beat_duration_sec": sex_arc_rep.get("beat_duration_sec"),
            "penetration_duration_ratio": sex_arc_rep.get("penetration_duration_ratio"),
            "has_foreplay": sex_arc_rep.get("has_foreplay"),
            "has_penetration": sex_arc_rep.get("has_penetration"),
            "has_climax_release": sex_arc_rep.get("has_climax_release"),
        },
        "detail_cu": {
            "ok": detail_cu_rep.get("ok"),
            "codes": detail_cu_rep.get("codes"),
            "detail_shots": detail_cu_rep.get("detail_shots"),
        },
        "both_undress": {
            "ok": both_undress_rep.get("ok"),
            "codes": both_undress_rep.get("codes"),
            "partner_stated_n": both_undress_rep.get("partner_stated_n"),
            "weak_hero": both_undress_rep.get("weak_hero"),
            "weak_partner": both_undress_rep.get("weak_partner"),
        },
        "size_ladder": {
            "ok": size_rep.get("ok"),
            "codes": size_rep.get("codes"),
            "ranks": size_rep.get("ranks"),
        },
        "note": (
            "Sex floor ≥50% duration (max IRON); undress; VO spice/extreme; coitus six-beat; "
            "sex arc 四拍; detail CU; size ladder; pose variety; montage craft. "
            "See adult-max-playbook.md"
        ),
    }


# Prompt / asset signals that mean multi-heroine (elastic; single is default)
_MULTI_HEROINE_PROMPT_MARKERS: tuple[str, ...] = (
    "双女主",
    "雙女主",
    "多女主",
    "两个女",
    "兩個女",
    "两位女",
    "兩位女",
    "两女",
    "兩女",
    "三个女",
    "三女",
    "百合双",
    "双飞",
    "雙飛",
    "3p女",
    "3P女",
    "两位女主",
    "兩位女主",
    "dual heroine",
    "dual heroines",
    "two heroines",
    "two girls",
    "multi heroine",
    "multi-heroine",
    "multiple heroines",
    "threesome girls",
)
_MALE_CAST_IDS = frozenset(
    {
        "partner",
        "male",
        "hero_m",
        "him",
        "man",
        "boy",
        "guy",
        "男主",
        "男",
        "彼氏",
        "boyfriend",
    }
)


def resolve_heroine_cast_mode(
    *,
    multi_heroine: object | None = None,
    cast_mode: object | None = None,
    heroine_ids: list[str] | None = None,
    cast_ids: list[str] | None = None,
    cast_masters: dict[str, Any] | None = None,
    prompt_blob: str = "",
    female_ref_image_count: int | None = None,
) -> dict[str, Any]:
    """Decide single vs multi heroine elastically from prompt / images / explicit fields.

    Default is **single**. Multi only when evidence is clear (user said so, ≥2 heroine
    ids, ≥2 female cast masters, or ≥2 female ref images with multi cue).
    """
    reasons: list[str] = []
    heroines = [str(x).strip() for x in (heroine_ids or []) if str(x).strip()]
    cast = [str(x).strip() for x in (cast_ids or []) if str(x).strip()]
    masters = cast_masters if isinstance(cast_masters, dict) else {}
    master_ids = [str(k).strip() for k in masters if str(k).strip()]
    # Female master candidates = masters not clearly male-coded
    female_masters = [
        m for m in master_ids if m.lower() not in _MALE_CAST_IDS and "male" not in m.lower()
    ]
    blob = (prompt_blob or "").strip()
    blob_l = blob.lower()
    prompt_multi = any(m in blob for m in _MULTI_HEROINE_PROMPT_MARKERS) or any(
        m in blob_l for m in _MULTI_HEROINE_PROMPT_MARKERS if m.isascii()
    )
    if prompt_multi:
        reasons.append("prompt_markers")

    # Explicit cast_mode wins when single|multi
    mode_raw = str(cast_mode or "").strip().lower()
    if mode_raw in {"single", "1", "solo"}:
        return {
            "mode": "single",
            "active": False,
            "heroine_ids": heroines[:1] if heroines else (female_masters[:1] or cast[:1]),
            "reasons": ["explicit_cast_mode=single"],
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }
    if mode_raw in {"multi", "multiple", "dual"}:
        if len(heroines) < 2 and len(female_masters) >= 2:
            heroines = female_masters
        reasons.append("explicit_cast_mode=multi")
        return {
            "mode": "multi",
            "active": True,
            "heroine_ids": heroines if len(heroines) >= 2 else female_masters,
            "reasons": reasons,
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }

    # Explicit multi_heroine bool
    if multi_heroine is False or str(multi_heroine).strip().lower() in {
        "0",
        "false",
        "no",
        "off",
        "single",
    }:
        return {
            "mode": "single",
            "active": False,
            "heroine_ids": heroines[:1] if heroines else (female_masters[:1] or []),
            "reasons": ["explicit_multi_heroine=false"],
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }
    if multi_heroine is True or str(multi_heroine).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        if len(heroines) < 2 and len(female_masters) >= 2:
            heroines = list(female_masters)
        reasons.append("explicit_multi_heroine=true")
        return {
            "mode": "multi",
            "active": True,
            "heroine_ids": heroines,
            "reasons": reasons,
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }

    # Evidence-based auto
    if len(heroines) >= 2:
        reasons.append("heroine_ids>=2")
    if len(female_masters) >= 2:
        reasons.append("cast_masters_female>=2")
    ref_n = int(female_ref_image_count or 0)
    if ref_n >= 2 and prompt_multi:
        reasons.append("female_ref_images>=2+prompt")
    elif ref_n >= 2 and len(female_masters) >= 2:
        reasons.append("female_ref_images>=2+masters")

    # Weak: two female-looking cast ids only when prompt also multi
    if not reasons and prompt_multi and len(cast) >= 2:
        cand = [c for c in cast if c.lower() not in _MALE_CAST_IDS]
        if len(cand) >= 2:
            heroines = cand
            reasons.append("prompt_multi+cast_ids")

    if reasons and (
        len(heroines) >= 2 or len(female_masters) >= 2 or (prompt_multi and ref_n >= 2)
    ):
        if len(heroines) < 2 and len(female_masters) >= 2:
            heroines = list(female_masters)
        return {
            "mode": "multi",
            "active": True,
            "heroine_ids": heroines,
            "reasons": reasons,
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }

    # Default single — one primary heroine
    single_id = (
        (heroines[0] if heroines else None)
        or (female_masters[0] if female_masters else None)
        or (cast[0] if cast else "hero")
    )
    return {
        "mode": "single",
        "active": False,
        "heroine_ids": [single_id] if single_id else [],
        "reasons": ["default_single"],
        "prompt_multi": prompt_multi,
        "female_master_count": len(female_masters),
        "female_ref_image_count": female_ref_image_count,
        "note": (
            "Single-heroine default. Multi only if prompt/images/cast evidence "
            "or cast_mode/multi_heroine/heroine_ids say so."
        ),
    }


def lint_multi_heroine(
    shots: list[dict[str, Any]],
    *,
    cast_ids: list[str] | None = None,
    heroine_ids: list[str] | None = None,
    active: bool | None = None,
    cast_mode: str | None = None,
) -> dict[str, Any]:
    """Soft lint for multi-heroine only when mode is multi / active.

    Single-heroine films: no dual/focal-gap warnings (elastic default).
    """
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    heroines = [str(x).strip() for x in (heroine_ids or []) if str(x).strip()]
    cast = [str(x).strip() for x in (cast_ids or []) if str(x).strip()]
    mode = (cast_mode or "").strip().lower()
    is_multi = bool(active) if active is not None else (mode == "multi" or len(heroines) >= 2)

    if not is_multi:
        return {
            "ok": True,
            "codes": [],
            "warning_count": 0,
            "issues": [],
            "heroine_ids": heroines[:1] if heroines else [],
            "cast_ids": cast,
            "focal_set": [],
            "mode": "single",
            "active": False,
            "note": "cast_mode=single — multi-heroine lint skipped (elastic default)",
        }

    focals: set[str] = set()
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        fc = str(dsl.get("focal_character") or shot.get("focal_character") or "").strip()
        if fc:
            focals.add(fc)

    if len(heroines) >= 2:
        missing_focus = [h for h in heroines if h not in focals]
        if missing_focus:
            codes.append("MULTI_HEROINE_FOCAL_GAP")
            issues.append(
                {
                    "code": "MULTI_HEROINE_FOCAL_GAP",
                    "severity": "warning",
                    "message": (
                        f"multi-heroine cast {heroines} but no shot focal_character for "
                        f"{missing_focus} — give each heroine ≥1 POV/stance beat"
                    ),
                }
            )
        # dual/pair beats recommended
        has_dual = False
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            vp = str(dsl.get("viewpoint") or "").lower()
            if vp == "dual" or str(shot.get("heat_phase") or "") == "climax":
                # weak dual signal
                if vp == "dual":
                    has_dual = True
        if not has_dual and len(heroines) >= 2:
            codes.append("MULTI_HEROINE_NO_DUAL")
            issues.append(
                {
                    "code": "MULTI_HEROINE_NO_DUAL",
                    "severity": "warning",
                    "message": (
                        "≥2 heroines but no viewpoint=dual shot — "
                        "add at least one two-shot / 同框 for relationship peak"
                    ),
                }
            )

    if len(cast) >= 3 and len(focals) < 2:
        codes.append("MULTI_CAST_FLAT_FOCAL")
        issues.append(
            {
                "code": "MULTI_CAST_FLAT_FOCAL",
                "severity": "warning",
                "message": (
                    f"cast has {len(cast)} ids but focal variety only {sorted(focals)} — "
                    "rotate focal_character across heroines/partner"
                ),
            }
        )

    return {
        "ok": len(issues) == 0,
        "codes": sorted(set(codes)),
        "warning_count": len(issues),
        "issues": issues,
        "heroine_ids": heroines,
        "cast_ids": cast,
        "focal_set": sorted(focals),
        "mode": "multi",
        "active": True,
        "note": "Multi-heroine active — see references/ecchi-story.md §女主弹性 · character-stance.md",
    }
