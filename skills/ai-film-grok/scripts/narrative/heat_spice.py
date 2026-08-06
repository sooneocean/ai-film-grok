"""Spice pack."""
from __future__ import annotations

import re
from typing import Any

from edit_policy_shared import PolicyError
from heat_coitus import resolve_coitus_beat
from heat_phase import (
    DEFAULT_BARE_PEAK_REQUIRED,
    DEFAULT_SHOT_DURATION_SEC,
    SEX_PHASES,
    infer_heat_phase,
)
from heat_wardrobe import (
    PHASE_WARDROBE_FLOOR,
    SEX_WARDROBE_OK,
    SEX_WARDROBE_STRONG,
    WARDROBE_STATES,
    WARDROBE_UNDRESS_RANK,
    _EXPOSED_WARDROBE_MARKERS,
    _FULL_DRESS_MARKERS,
    _UNDRESS_ACTION_MARKERS,
)

__all__ = ["SPICE_LEVELS","HARDCORE_CRAFT_SPINE","_NAR_EXTREME_MARKERS","_NAR_MILD_ONLY_MARKERS","_NAR_SPICE_MARKERS","_NAR_SEX_VERB_MARKERS","_NAR_LITERARY_ONLY_HINTS","_TEMPLATE_NAR_POLLUTION_MARKERS","is_template_nar_pollution","lint_user_source_fidelity","nar_has_spice","nar_has_sex_verb","nar_has_extreme_spice","normalize_spice_level","lint_sex_vo_spice","apply_vo_spice_auto","suggest_vo_lines"]
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

