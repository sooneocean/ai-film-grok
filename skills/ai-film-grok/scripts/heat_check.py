#!/usr/bin/env python3
"""One-page adult heat gate report: duration / wardrobe / VO / coitus / size ladder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from edit_policy import compute_erotic_impact_score, lint_heat_arc
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


def heat_check(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    if not spec:
        return {"ok": False, "error": "missing film-spec.json", "root": str(root)}
    shots = _flat_shots(spec)
    intent = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    audience = intent.get("audience_profile") or spec.get("audience_profile")
    heat_scale = spec.get("heat_scale")
    cg = spec.get("coitus_grammar") if isinstance(spec.get("coitus_grammar"), dict) else None
    craft = spec.get("edit_craft")
    craft_list = craft if isinstance(craft, list) else ([craft] if craft else None)
    rep = lint_heat_arc(
        shots,
        heat_scale=str(heat_scale) if heat_scale else None,
        intimacy_min_ratio=spec.get("intimacy_min_ratio"),
        setup_max_ratio=spec.get("setup_max_ratio"),
        sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
        audience_profile=str(audience) if audience else None,
        advise=True,
        coitus_grammar=cg,
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
    if str(heat_scale or "").lower() == "max":
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
        "sfx_shots": sfx_n,
        "sound_plan_accents": plan_sfx,
        "sex_sfx_accents": sex_sfx,
    }
    hard_codes = [
        c
        for c in (rep.get("codes") or [])
        if c.startswith("HEAT_")
        or c.startswith("COITUS_")
        or c.startswith("SIZE_")
        or c.startswith("SEX_ARC_")
        or c.startswith("SEX_DETAIL_")
        or c.startswith("SEX_BOTH_")
        or c.startswith("MONTAGE_")
        or c == "SEX_POSE_STALE"
    ]
    if sensory and not sensory.get("ok"):
        hard_codes.extend(str(code) for code in sensory.get("codes") or [])
    sex_arc = rep.get("sex_arc") or {}
    detail = rep.get("detail_cu") or {}
    return {
        "ok": bool(rep.get("ok")) and (sensory is None or bool(sensory.get("ok"))),
        "root": str(root),
        "heat_scale": heat_scale,
        "audience_profile": audience,
        "shot_count": len(shots),
        "sex_duration_ratio": rep.get("sex_duration_ratio"),
        "codes": rep.get("codes"),
        "warning_count": rep.get("warning_count"),
        "gates": gates,
        "hard_relevant_codes": hard_codes,
        "erotic_impact": impact,
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
            f"wardrobe_ok={(rep.get('wardrobe') or {}).get('ok')} "
            f"vo_ok={(rep.get('vo_spice') or {}).get('ok')} "
            f"coitus_ok={(rep.get('coitus') or {}).get('ok')} "
            f"size_ok={(rep.get('size_ladder') or {}).get('ok')} "
            f"pose_u={(rep.get('poses') or {}).get('unique')} "
            f"sfx={sfx_n}/{plan_sfx}sex={sex_sfx} "
            f"codes={','.join((rep.get('codes') or [])[:8]) or 'none'}"
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
    from edit_policy import apply_vo_spice_auto
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
