#!/usr/bin/env python3
"""One-page adult heat gate report: duration / wardrobe / VO / coitus / size ladder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from edit_policy import (
    apply_impact_boost_patches,
    apply_vo_spice_auto,
    compute_erotic_impact_score,
    lint_ecchi_checklist,
    lint_heat_arc,
    suggest_impact_boost_actions,
)
from util import read_json


def _flat_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for sc in spec.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        for sh in sc.get("shots") or []:
            if isinstance(sh, dict):
                shots.append(sh)
    return shots



def _is_explicit_max_spec(spec: dict[str, Any]) -> bool:
    """True only when user/plan explicitly pulled max IRON (not plot-driven hot)."""
    pin = str(spec.get("heat_pinned_by") or spec.get("pinned_by") or "").strip().lower()
    scale = str(spec.get("heat_scale") or "").strip().lower()
    if pin in {"plot_driven", "user_soft"}:
        return False
    if pin == "explicit_max":
        return True
    if scale == "max" and pin not in {"plot_driven", "user_soft"}:
        return True
    if spec.get("challenge_max_scale") is True and scale == "max":
        return True
    return False


def heat_check(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    if not spec:
        return {"ok": False, "error": "missing film-spec.json", "root": str(root)}
    shots = _flat_shots(spec)
    intent = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    audience = intent.get("audience_profile") or spec.get("audience_profile")
    heat_scale = spec.get("heat_scale")
    explicit_max = _is_explicit_max_spec(spec)
    # Plot-driven hot: force advise path (lint treats non-max softer; never pretend max)
    lint_scale = str(heat_scale) if heat_scale else None
    if not explicit_max and str(heat_scale or "").lower() == "max":
        lint_scale = "hot"
    cg = spec.get("coitus_grammar") if isinstance(spec.get("coitus_grammar"), dict) else None
    craft = spec.get("edit_craft")
    craft_list = craft if isinstance(craft, list) else ([craft] if craft else None)
    rep = lint_heat_arc(
        shots,
        heat_scale=lint_scale,
        intimacy_min_ratio=spec.get("intimacy_min_ratio"),
        setup_max_ratio=spec.get("setup_max_ratio"),
        sex_min_duration_ratio=spec.get("sex_min_duration_ratio") if explicit_max else None,
        audience_profile=str(audience) if audience else None,
        advise=True,
        coitus_grammar=cg if explicit_max else None,
        spice_level=spec.get("spice_level"),
        edit_craft=craft_list,
    )
    sfx_n = sum(
        1
        for sh in shots
        if isinstance(sh, dict) and (sh.get("sound_cues") or sh.get("_sfx_kinds_from_cues"))
    )
    sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    plan_sfx = sum(
        1 for e in (sp.get("events") or []) if isinstance(e, dict) and e.get("type") == "sfx_accent"
    )
    sex_sfx = sum(1 for e in (sp.get("events") or []) if isinstance(e, dict) and e.get("sex_sfx"))
    impact = compute_erotic_impact_score(
        shots,
        heat_scale=str(heat_scale) if heat_scale else None,
        heat_rep=rep,
    )
    sensory: dict[str, Any] | None = None
    if explicit_max and str(heat_scale or "").lower() == "max":
        try:
            from adult_max_director import build_evidence

            sensory = build_evidence(root, write=False)
            media_ok = bool(sensory.get("ok"))
            impact["spec_score"] = impact.get("score")
            impact["media_score"] = 100 if media_ok else 0
            impact["score"] = round(
                (int(impact.get("spec_score") or 0) + impact["media_score"]) / 2
            )
            impact["grade"] = "S" if media_ok and impact["score"] >= 90 else impact.get("grade")
        except (OSError, ValueError):
            sensory = {"ok": False, "codes": ["ADULT_MAX_EVIDENCE_UNAVAILABLE"]}
    # Wave 3: S-boost plan + 色气 checklist + mute-frame advisory (no fake pixel CV)
    # Prefer field/spec score for boost planning when media halves the grade
    boost_impact = {
        "score": impact.get("spec_score", impact.get("score")),
        "bands": impact.get("bands") or {},
        "grade": impact.get("grade"),
    }
    boost = suggest_impact_boost_actions(
        shots,
        heat_scale=str(heat_scale) if heat_scale else None,
        heat_rep=rep,
        impact=boost_impact,
        target_score=90.0 if explicit_max else 75.0,
    )
    ecchi = lint_ecchi_checklist(shots, heat_scale=str(heat_scale) if heat_scale else None)
    mute_adv = mute_frame_advisory(shots, heat_scale=str(heat_scale) if heat_scale else None)
    gates = {
        "sex_duration": {
            "ratio": rep.get("sex_duration_ratio"),
            "floor": rep.get("sex_duration_floor"),
            "ok": "HEAT_SEX_DURATION_LOW" not in (rep.get("codes") or []),
        },
        "wardrobe": {
            "ok": (rep.get("wardrobe") or {}).get("ok"),
            "codes": (rep.get("wardrobe") or {}).get("codes"),
        },
        "vo_spice": {
            "ok": (rep.get("vo_spice") or {}).get("ok"),
            "spice_ratio": (rep.get("vo_spice") or {}).get("spice_ratio"),
            "spice_level": rep.get("spice_level"),
            "too_mild": (rep.get("vo_spice") or {}).get("too_mild_shots"),
        },
        "vo_motion": rep.get("vo_motion") or {},
        "poses": rep.get("poses") or {},
        "montage": rep.get("montage") or {},
        "coitus": rep.get("coitus") or {},
        "sex_arc": rep.get("sex_arc") or {},
        "detail_cu": rep.get("detail_cu") or {},
        "both_undress": rep.get("both_undress") or {},
        "size_ladder": rep.get("size_ladder") or {},
        "adult_max_sensory": sensory,
        "erotic_impact": impact,
        "impact_boost": boost,
        "ecchi_checklist": ecchi,
        "mute_frame_advisory": mute_adv,
        "sfx_shots": sfx_n,
        "sound_plan_accents": plan_sfx,
        "sex_sfx_accents": sex_sfx,
    }
    # Queue/final hard_fail must not treat HEAT_ADVISORY_* as hard (advisory = soft).
    # Plot-driven (non explicit_max): all heat ratio / max IRON codes are advisory only.
    hard_codes = [
        c
        for c in (rep.get("codes") or [])
        if (
            (
                c.startswith("HEAT_")
                and not c.startswith("HEAT_ADVISORY_")
            )
            or c.startswith("COITUS_")
            or c.startswith("SIZE_")
            or c.startswith("SEX_ARC_")
            or c.startswith("SEX_DETAIL_")
            or c.startswith("SEX_BOTH_")
            or c.startswith("MONTAGE_")
            or c == "SEX_POSE_STALE"
        )
    ]
    if not explicit_max:
        hard_codes = []
    if sensory and not sensory.get("ok") and explicit_max:
        hard_codes.extend(str(code) for code in sensory.get("codes") or [])
    # max + ecchi_checklist_strict: thin checklist hard-fails heat check
    if (
        explicit_max
        and str(heat_scale or "").lower() == "max"
        and spec.get("ecchi_checklist_strict") is True
        and not ecchi.get("ok")
    ):
        hard_codes.extend(str(c) for c in (ecchi.get("codes") or []))
    sex_arc = rep.get("sex_arc") or {}
    detail = rep.get("detail_cu") or {}
    codes_all = list(rep.get("codes") or [])
    codes_all.extend(ecchi.get("codes") or [])
    ok_plot = True if not explicit_max else bool(rep.get("ok"))
    return {
        "ok": ok_plot
        and (sensory is None or bool(sensory.get("ok")))
        and (
            not explicit_max
            or spec.get("ecchi_checklist_strict") is not True
            or bool(ecchi.get("ok"))
            or str(heat_scale or "").lower() != "max"
        ),
        "root": str(root),
        "heat_scale": heat_scale,
        "heat_pinned_by": spec.get("heat_pinned_by") or spec.get("pinned_by"),
        "explicit_max": explicit_max,
        "audience_profile": audience,
        "shot_count": len(shots),
        "sex_duration_ratio": rep.get("sex_duration_ratio"),
        "codes": codes_all,
        "warning_count": rep.get("warning_count"),
        "gates": gates,
        "hard_relevant_codes": hard_codes,
        "erotic_impact": impact,
        "impact_boost": boost,
        "ecchi_checklist": ecchi,
        "mute_frame_advisory": mute_adv,
        "adult_max_sensory": sensory,
        "strict_flags": {
            "sex_floor_strict": spec.get("sex_floor_strict"),
            "sex_wardrobe_strict": spec.get("sex_wardrobe_strict"),
            "sex_vo_strict": spec.get("sex_vo_strict"),
            "heat_arc_strict": spec.get("heat_arc_strict"),
            "coitus_strict": spec.get("coitus_strict"),
            "size_ladder_strict": spec.get("size_ladder_strict"),
            "sex_arc_strict": spec.get("sex_arc_strict"),
            "sex_detail_cu_strict": spec.get("sex_detail_cu_strict"),
            "both_undress_strict": spec.get("both_undress_strict"),
            "pose_strict": spec.get("pose_strict"),
            "ecchi_checklist_strict": spec.get("ecchi_checklist_strict"),
        },
        "spice_level": rep.get("spice_level") or spec.get("spice_level"),
        "sex_duration_floor": rep.get("sex_duration_floor"),
        "intimacy_ratio": rep.get("intimacy_ratio"),
        "bare_peak_ok": (rep.get("wardrobe") or {}).get("bare_peak_ok"),
        "line": (
            f"heat={heat_scale} spice={rep.get('spice_level') or spec.get('spice_level')} "
            f"sex={rep.get('sex_duration_ratio')}/floor={rep.get('sex_duration_floor')} "
            f"intimacy={rep.get('intimacy_ratio')} "
            f"bare={(rep.get('wardrobe') or {}).get('bare_peak_ok')} "
            f"arc_ok={sex_arc.get('ok')} pen_ratio={sex_arc.get('penetration_duration_ratio')} "
            f"detail_cu={','.join(detail.get('detail_shots') or []) or 'none'} "
            f"impact={impact.get('grade')}:{impact.get('score')} "
            f"ecchi={ecchi.get('score')}/{ecchi.get('need')} "
            f"boost_actions={len(boost.get('actions') or [])} "
            f"wardrobe_ok={(rep.get('wardrobe') or {}).get('ok')} "
            f"vo_ok={(rep.get('vo_spice') or {}).get('ok')} "
            f"coitus_ok={(rep.get('coitus') or {}).get('ok')} "
            f"size_ok={(rep.get('size_ladder') or {}).get('ok')} "
            f"pose_u={(rep.get('poses') or {}).get('unique')} "
            f"sfx={sfx_n}/{plan_sfx}sex={sex_sfx} "
            f"codes={','.join(codes_all[:8]) or 'none'}"
        ),
    }


def mute_frame_advisory(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """List act/climax shots that still need human mute-frame coitus evidence.

    Honest: no skin-tone CV. Agent must score --score-coitus on review-shot.
    """
    from edit_policy import infer_heat_phase

    scale = (heat_scale or "").strip().lower()
    if scale not in {"max", "hot"}:
        return {"ok": True, "enabled": False, "shots": [], "note": "not max/hot"}
    need: list[dict[str, Any]] = []
    for sh in shots:
        if not isinstance(sh, dict):
            continue
        ph = infer_heat_phase(sh)
        if ph not in {"act", "climax"}:
            continue
        sid = str(sh.get("id") or "?")
        need.append(
            {
                "shot_id": sid,
                "heat_phase": ph,
                "action": "review-shot --score-coitus 4..5 (mute-frame 办事可读)",
                "hint": "静音一帧能读结合/抽送才算；拥抱=fail",
            }
        )
    return {
        "ok": True,
        "enabled": True,
        "count": len(need),
        "shots": need,
        "note": (
            "pixel advisory only — human mute-frame required; "
            "no automated genital/skin CV in this build"
        ),
    }


def build_heat_report(
    spec: dict[str, Any], shots: list[dict[str, Any]], *, total_duration_sec: float
) -> dict[str, Any]:
    """Build the historical contract report without requiring a film root."""

    rep = lint_heat_arc(
        shots,
        heat_scale=str(spec.get("heat_scale") or "") or None,
        sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
        advise=True,
    )
    rep.setdefault("sex_duration_floor", float(spec.get("sex_min_duration_ratio") or 0.50))
    rep.setdefault("sex_duration_ratio", 0.0)
    return rep


def heat_vo_suggest(
    root: Path,
    *,
    shot_id: str | None = None,
) -> dict[str, Any]:
    """Suggest stronger adult nar lines for a shot or all act shots."""
    from edit_policy import infer_heat_phase, resolve_coitus_beat, suggest_vo_lines

    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    shots = _flat_shots(spec)
    spice = str(spec.get("spice_level") or "explicit")
    out: list[dict[str, Any]] = []
    for sh in shots:
        sid = str(sh.get("id") or "")
        if shot_id and sid != shot_id:
            continue
        ph = infer_heat_phase(sh)
        cb = resolve_coitus_beat(sh)
        if shot_id or ph in {"act", "climax", "foreplay", "setup", "afterglow"}:
            lines = suggest_vo_lines(heat_phase=ph, coitus_beat=cb, spice_level=spice)
            out.append(
                {
                    "id": sid,
                    "heat_phase": ph,
                    "coitus_beat": cb,
                    "current_nar": sh.get("nar"),
                    "suggestions": lines,
                }
            )
    return {
        "ok": True,
        "root": str(root),
        "spice_level": spice,
        "shots": out,
        "note": "Copy a suggestion into film-spec nar; re-run write-spec / heat check",
    }


def heat_agent_status(root: Path) -> dict[str, Any]:
    """Compact adult-max gate for dispatch / next / preflight (Wave 4).

    Returns ready-to-inject next action when heat needs work before bulk/final.
    """
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    if not spec:
        return {"active": False, "ok": True, "reason": "no_spec"}
    heat = str(spec.get("heat_scale") or "").strip().lower()
    if heat not in {"max", "hot", "high"}:
        return {"active": False, "ok": True, "reason": "not_adult_max"}
    if spec.get("adult_max_iron") is False:
        return {"active": False, "ok": True, "reason": "adult_max_iron_false"}
    explicit_max = _is_explicit_max_spec(spec)
    # Plot-driven hot: advisory only — never hard-block bulk for max IRON floors
    if not explicit_max:
        return {
            "active": True,
            "ok": True,
            "advisory": True,
            "reason": "plot_driven_heat",
            "heat_scale": heat,
            "heat_pinned_by": spec.get("heat_pinned_by") or "plot_driven",
            "why": "plot-driven heat: max IRON floors advisory; no bulk hard-fail",
            "next_cmd": f'aifilm heat check --root "{root}"',
        }

    # Prefer cached write-spec scorecard; fall back to full heat_check (may be heavy)
    impact = spec.get("_erotic_impact") if isinstance(spec.get("_erotic_impact"), dict) else None
    heat_arc = spec.get("_heat_arc") if isinstance(spec.get("_heat_arc"), dict) else None
    boost_receipt = read_json(root / "receipts" / "heat-boost.json") or {}
    try:
        full = heat_check(root)
    except Exception as exc:  # noqa: BLE001
        return {
            "active": True,
            "ok": False,
            "error": str(exc)[:200],
            "next_cmd": f'aifilm heat check --root "{root}"',
            "why": "heat check failed to run",
        }
    impact = full.get("erotic_impact") or impact or {}
    boost = (
        full.get("impact_boost")
        or (boost_receipt.get("plan") if isinstance(boost_receipt, dict) else {})
        or {}
    )
    ecchi = full.get("ecchi_checklist") or {}
    # Prefer field/spec score — media sensory often fails pre-bulk and must not block planning
    score = float(impact.get("spec_score") or impact.get("score") or 0.0)
    floor = float(spec.get("erotic_impact_floor") or 75.0)
    try:
        target_s = float(spec.get("erotic_impact_target_s") or 90.0)
    except (TypeError, ValueError):
        target_s = 90.0
    raw_codes = list(full.get("hard_relevant_codes") or full.get("codes") or [])
    # Ignore media-only adult_max evidence until clips exist
    codes = [c for c in raw_codes if not str(c).startswith("ADULT_MAX_")]
    # Soft / warning-class codes must not block media-queue (Wave 5 hard_fail).
    # Advisories, VO mildness, escalation plateau warnings, ratio warnings stay visible
    # in codes but only true scale fails hard-block bulk.
    _queue_soft = {
        "HEAT_ESCALATION_STALL",
        "HEAT_VO_SEX_VERB_WEAK",
        "HEAT_VO_SPICE_TOO_MILD",
        "HEAT_VO_SPICE_MISSING",
        "HEAT_VO_SPICE_RATIO_LOW",
        "HEAT_INTIMACY_RATIO_LOW",
        "HEAT_SETUP_RATIO_HIGH",
        "SIZE_STACK_FLAT",
    }
    queue_hard_codes = [
        c
        for c in codes
        if c not in _queue_soft and not str(c).startswith("HEAT_ADVISORY_")
    ]
    needs_boost = bool(boost.get("needed")) or score + 1e-9 < target_s
    below_a = score + 1e-9 < floor
    field_ok = bool((full.get("gates") or {}).get("sex_duration", {}).get("ok", True))
    heat_arc_ok = bool((heat_arc or (full.get("gates") or {}).get("sex_arc") or {}).get("ok", True))
    # hard when below A or true hard field codes remain (not media-only, not soft warnings)
    hard_fail = below_a or bool(queue_hard_codes)
    # Wave 6: final needs S-grade scale (not only A) + field/arc ok
    final_ok = (not hard_fail) and (not needs_boost) and field_ok and heat_arc_ok
    next_cmd = None
    why = None
    if hard_fail or needs_boost or not final_ok:
        next_cmd = f'aifilm heat boost --root "{root}" --apply'
        why = (
            f"adult max heat: impact={impact.get('grade')}:{score} "
            f"(A≥{floor} S≥{target_s}) ecchi={ecchi.get('score')}/{ecchi.get('need')} "
            f"actions={len(boost.get('actions') or [])} "
            f"codes={','.join(codes[:6]) or 'none'}"
        )
        if hard_fail:
            why = "HARD " + why
        elif not final_ok and not needs_boost:
            why = "FINAL " + why
    return {
        "active": True,
        "ok": not hard_fail and field_ok,
        "needs_boost": needs_boost,
        "hard_fail": hard_fail,
        "final_ok": final_ok,
        "score": score,
        "grade": impact.get("grade"),
        "floor": floor,
        "target_s": target_s,
        "ecchi_score": ecchi.get("score"),
        "ecchi_need": ecchi.get("need"),
        "boost_actions": len(boost.get("actions") or []),
        "codes": codes[:12],
        "queue_hard_codes": queue_hard_codes[:12],
        "heat_arc_ok": heat_arc_ok,
        "field_ok": field_ok,
        "next_cmd": next_cmd,
        "why": why,
        "mute_frame_n": (full.get("mute_frame_advisory") or {}).get("count"),
        "line": full.get("line"),
    }


def heat_boost(
    root: Path,
    *,
    apply: bool = False,
    target_score: float = 90.0,
) -> dict[str, Any]:
    """Impact S boost plan; optional field patches (duration/bare/detail/verbs/VO).

    Writes receipts/heat-boost.json. Never lowers heat_scale.
    """
    from util import write_json

    root = Path(root).expanduser().resolve()
    spec_path = root / "film-spec.json"
    spec = read_json(spec_path) or {}
    if not spec:
        return {"ok": False, "error": "missing film-spec.json", "root": str(root)}
    heat = str(spec.get("heat_scale") or "").strip().lower()
    shots = _flat_shots(spec)
    rep = lint_heat_arc(
        shots,
        heat_scale=heat or None,
        sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
        advise=True,
        spice_level=spec.get("spice_level"),
    )
    impact = compute_erotic_impact_score(shots, heat_scale=heat or None, heat_rep=rep)
    plan = suggest_impact_boost_actions(
        shots,
        heat_scale=heat or None,
        heat_rep=rep,
        impact=impact,
        target_score=target_score,
    )
    applied: dict[str, Any] = {"patches": None, "vo": None}
    if apply and heat in {"max", "hot"}:
        patches = apply_impact_boost_patches(shots, list(plan.get("actions") or []))
        applied["patches"] = patches
        vo = apply_vo_spice_auto(shots, spice_level=str(spec.get("spice_level") or "extreme"))
        applied["vo"] = vo
        # re-score after patches
        rep2 = lint_heat_arc(
            shots,
            heat_scale=heat or None,
            sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
            advise=True,
            spice_level=spec.get("spice_level"),
        )
        impact_after = compute_erotic_impact_score(shots, heat_scale=heat or None, heat_rep=rep2)
        plan["score_after"] = impact_after.get("score")
        plan["grade_after"] = impact_after.get("grade")
        write_json(spec_path, spec)
    path = root / "receipts" / "heat-boost.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "ok": True,
        "kind": "heat-impact-boost",
        "apply": apply,
        "heat_scale": heat or None,
        "plan": plan,
        "applied": applied,
        "ecchi": lint_ecchi_checklist(shots, heat_scale=heat or None),
        "mute_frame_advisory": mute_frame_advisory(shots, heat_scale=heat or None),
    }
    write_json(path, receipt)
    return {
        "ok": True,
        "root": str(root),
        "path": str(path),
        "plan": plan,
        "applied": applied,
        "line": (
            f"heat-boost apply={apply} score={plan.get('score')}→"
            f"{plan.get('score_after', plan.get('score'))} "
            f"actions={len(plan.get('actions') or [])} "
            f"patched={(applied.get('patches') or {}).get('changed')}"
        ),
    }


def heat_soften_compensate(
    root: Path,
    *,
    note: str = "",
    apply: bool = False,
) -> dict[str, Any]:
    """Dual-track moderation compensation: VO + SFX + L4 insert checklist.

    Never lowers heat_scale. When apply=True, rewrites weak nar + injects sex SFX
    into film-spec sound_plan (still does not invent stills).
    """
    from util import write_json

    root = Path(root).expanduser().resolve()
    spec_path = root / "film-spec.json"
    spec = read_json(spec_path) or {}
    if not spec:
        return {"ok": False, "error": "missing film-spec.json", "root": str(root)}
    heat = str(spec.get("heat_scale") or "").strip().lower()
    shots = _flat_shots(spec)
    checklist = [
        "Rewrite act/climax nar with denser sex verbs (沉腰/吃进/办穿)",
        "Add insert_cut craft or L4 body/fabric still (coverage_role=detail)",
        "Ensure sound_cues impact/breath on act; sex_sfx accents present",
        "Top-shelf suggestive pelvis contact when true bare is blocked",
        "Do NOT set heat_scale to medium/soft",
        "Do NOT fake penetration with hug-only stills",
    ]
    applied: dict[str, Any] = {"vo": None, "sfx": None, "music_energy": None}
    if apply and heat in {"max", "hot"}:
        spice = str(spec.get("spice_level") or "extreme")
        vo_fix = apply_vo_spice_auto(shots, spice_level=spice)
        applied["vo"] = vo_fix
        try:
            from sound_plan import (
                default_sound_plan_for_film,
                inject_music_energy_spotting,
                inject_sex_sfx_from_shots,
            )

            sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else None
            if sp is None:
                sp = default_sound_plan_for_film(
                    vo_mode=str(spec.get("vo_mode") or "storyteller"),
                    tone=str((spec.get("director_intent") or {}).get("tone") or ""),
                    title=str(spec.get("title") or ""),
                )
            sp = inject_sex_sfx_from_shots(sp, shots, heat_scale=heat)
            sp = inject_music_energy_spotting(sp, shots, heat_scale=heat)
            spec["sound_plan"] = sp
            applied["sfx"] = {
                "sex_notes": list(sp.get("_notes") or [])[-2:],
                "music_spotting_n": len(sp.get("music_spotting") or []),
            }
            applied["music_energy"] = applied["sfx"]
        except Exception as exc:  # noqa: BLE001
            applied["sfx"] = {"error": str(exc)}
        # ensure heat stays max
        if heat == "max":
            spec["heat_scale"] = "max"
            spec.setdefault("spice_level", "extreme")
        write_json(spec_path, spec)
    # detail coverage advisory
    detail_ids = [
        str(sh.get("id") or "?")
        for sh in shots
        if str(sh.get("coverage_role") or (sh.get("dsl") or {}).get("coverage_role") or "").lower()
        == "detail"
        or "insert"
        in str(
            sh.get("shot_size")
            or ((sh.get("dsl") or {}).get("camera") or {}).get("shot_size")
            or ""
        ).lower()
    ]
    receipt = {
        "ok": True,
        "kind": "moderation-soften-compensate",
        "at": __import__("datetime")
        .datetime.now(__import__("datetime").UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "note": note or "moderation softed still/I2V",
        "heat_scale": heat or None,
        "heat_scale_must_stay": True,
        "apply": apply,
        "applied": applied,
        "detail_shots": detail_ids,
        "checklist": checklist,
        "compensation": {
            "vo_spice_up": True,
            "insert_l4": True,
            "sfx_flesh": True,
            "music_energy_follow": True,
        },
    }
    path = root / "receipts" / "moderation_soften.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, receipt)
    return {
        "ok": True,
        "root": str(root),
        "path": str(path),
        "receipt": receipt,
        "line": (
            f"soften-compensate apply={apply} heat={heat} "
            f"vo_fixed={(applied.get('vo') or {}).get('fixed')} "
            f"detail={','.join(detail_ids[:4]) or 'none'}"
        ),
    }
