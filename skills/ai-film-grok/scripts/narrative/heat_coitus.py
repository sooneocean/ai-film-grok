"""Coitus pack."""
from __future__ import annotations

from typing import Any

from edit_policy_shared import (
    _COITUS_PSEUDO_ONLY,
    _COITUS_READABLE_MARKERS,
    COITUS_BEATS,
    COITUS_REQUIRED_BEATS,
)
from heat_phase import SEX_PHASES, infer_heat_phase
from heat_wardrobe import resolve_wardrobe_state

__all__ = [
    "SEX_POSES",
    "COITUS_BEAT_DEFAULT_POSE",
    "COITUS_BEATS",
    "COITUS_REQUIRED_BEATS",
    "SEX_ARC_BEATS",
    "SEX_ARC_REQUIRED",
    "resolve_sex_pose",
    "_shot_visual_pose_blob",
    "shot_coitus_readable",
    "shot_coitus_pseudo_only",
    "resolve_coitus_beat",
    "lint_coitus_grammar",
    "resolve_sex_arc_beat",
    "_shot_has_penetration_verb",
    "_shot_has_release_marker",
    "lint_sex_arc",
    "lint_sex_pose_variety",
    "_SEX_ARC_PENETRATION_MARKERS",
    "_SEX_ARC_RELEASE_MARKERS",
    "_SEX_ARC_FOREPLAY_MARKERS",
]
def _shot_duration_sec(shot, default=6.0):
    try:
        d=float(shot.get("duration_sec") or default)
    except (TypeError, ValueError):
        d=default
    return 0.0 if d<0 else d
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

