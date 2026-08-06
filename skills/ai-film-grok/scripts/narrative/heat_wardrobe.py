"""Wardrobe pack."""
from __future__ import annotations

from typing import Any

from edit_policy_shared import PolicyError
from heat_phase import (
    DEFAULT_BARE_PEAK_REQUIRED,
    SEX_PHASES,
    infer_heat_phase,
)

__all__ = ["WARDROBE_STATES","WARDROBE_UNDRESS_RANK","SEX_WARDROBE_OK","SEX_WARDROBE_STRONG","PHASE_WARDROBE_FLOOR","_EXPOSED_WARDROBE_MARKERS","_UNDRESS_ACTION_MARKERS","_FULL_DRESS_MARKERS","_WARDROBE_START_POSE_HINT","_WARDROBE_SUBJECT_MUST_INCLUDE","_shot_visual_blob","normalize_wardrobe_state","resolve_wardrobe_state","shot_has_undress_action","wardrobe_undress_rank","_write_shot_wardrobe_state","apply_wardrobe_continuity","_ensure_start_pose_wardrobe","lint_sex_wardrobe","resolve_partner_wardrobe_state","lint_both_undress"]
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

def lint_both_undress(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Penetration window: heroine bare + partner ≥undressed when field present.

    When partner_wardrobe_state is omitted on all penetration shots, emit soft
    SEX_BOTH_UNDRESS_UNSTATED (info). When present but weak → SEX_BOTH_UNDRESS_MISSING.
    """
    from heat_coitus import _shot_has_penetration_verb, resolve_sex_arc_beat
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

