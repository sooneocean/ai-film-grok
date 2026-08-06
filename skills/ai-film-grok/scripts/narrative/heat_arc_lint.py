"""Heat arc orchestrator."""
from __future__ import annotations

from typing import Any

from heat_coitus import (
    lint_coitus_grammar,
    lint_sex_arc,
    lint_sex_pose_variety,
    resolve_coitus_beat,
)
from heat_impact import (
    ECCHI_CHECKLIST_ITEMS,
    lint_montage_craft,
    lint_sex_detail_cu,
    lint_size_ladder,
    lint_vo_motion_align,
)
from heat_phase import (
    ADVISORY_MAX_INTIMACY_RATIO,
    ADVISORY_MAX_SETUP_RATIO,
    ADVISORY_MAX_SEX_DURATION_RATIO,
    DEFAULT_SEX_DURATION_FLOOR,
    EXTREME_INTIMACY_FLOOR,
    EXTREME_SETUP_CEILING,
    HARDCORE_SEX_DURATION_TARGET,
    HEAT_PHASES,
    HOT_SEX_DURATION_FLOOR,
    INTIMACY_PHASES,
    SEX_PHASES,
    infer_heat_phase,
    lint_heat_escalation_challenge,
)
from heat_spice import lint_sex_vo_spice, lint_user_source_fidelity, normalize_spice_level
from heat_wardrobe import (
    lint_both_undress,
    lint_sex_wardrobe,
)

__all__ = ["_merge_sub_issues","_shot_duration_sec","lint_heat_arc","ECCHI_CHECKLIST_ITEMS"]
def _shot_duration_sec(shot: dict[str, Any], default: float = 6.0) -> float:
    try:
        return max(0.0, float(shot.get("duration_sec") or default))
    except (TypeError, ValueError):
        return default

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

