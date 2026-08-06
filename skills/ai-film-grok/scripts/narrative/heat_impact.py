"""Impact pack."""
from __future__ import annotations
from typing import Any
from edit_policy_shared import PolicyError
from heat_phase import SEX_PHASES, infer_heat_phase, normalize_heat_scale
from heat_coitus import _shot_has_penetration_verb, _shot_visual_pose_blob, lint_sex_arc, resolve_coitus_beat, resolve_sex_pose, shot_coitus_readable
from heat_wardrobe import resolve_wardrobe_state, shot_has_undress_action
from heat_spice import HARDCORE_CRAFT_SPINE, _NAR_SEX_VERB_MARKERS, nar_has_extreme_spice, nar_has_sex_verb, nar_has_spice
__all__ = ["ECCHI_CHECKLIST_ITEMS","_ECCHI_DISTANCE","_ECCHI_WARDROBE","_ECCHI_SENSORY","_ECCHI_POWER","_ECCHI_DOUBLE","_ECCHI_COMPLETE","lint_ecchi_checklist","suggest_impact_boost_actions","apply_impact_boost_patches","compute_erotic_impact_score","lint_sex_detail_cu","_is_detail_cu_shot","lint_size_ladder","_shot_size_rank","lint_vo_motion_align","lint_montage_craft"]
def _shot_duration_sec(shot, default=6.0):
    try:
        d=float(shot.get("duration_sec") or default)
    except (TypeError, ValueError):
        d=default
    return 0.0 if d<0 else d
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

