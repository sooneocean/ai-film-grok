"""Heat + cast + adult sensory tail of film_spec validation (W2 peel).

Structure-only. IRON floors and heat policy unchanged — body moved verbatim.
"""

from __future__ import annotations

import contextlib
from typing import Any

from edit_policy import (
    PolicyError,
    apply_heat_phase_defaults,
    apply_wardrobe_continuity,
    compute_erotic_impact_score,
    lint_heat_arc,
    lint_multi_heroine,
    normalize_heat_scale,
    resolve_heroine_cast_mode,
)
from plan.film_spec_lints import FilmSpecError


def apply_heat_cast_and_adult_tail(
    spec: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    film_root: Any | None = None,
) -> list[dict[str, Any]]:
    """Mutate spec/shots for heat/cast/adult sensory; return shots.

    Raises FilmSpecError on the same hard paths as the former inlined body.
    """
    # Heat + cast: elastic (no auto-pin heat_scale; metrics optional)
    try:
        heat_scale = normalize_heat_scale(spec.get("heat_scale"), default=None)
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc
    intent = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    # Do NOT auto-force heat_scale from keywords — agent/user sets it from the brief.
    if heat_scale is not None:
        spec["heat_scale"] = heat_scale
    # heat_phase fill only when asked (or when heat_scale already set and heat_phase_auto≠false)
    heat_phase_auto = spec.get("heat_phase_auto")
    if heat_phase_auto is True or (heat_scale is not None and heat_phase_auto is not False):
        filled_hp = apply_heat_phase_defaults(shots)
        if filled_hp:
            notes = list(spec.get("_heat_notes") or [])
            notes.append(f"heat_phase filled (soft): {','.join(filled_hp[:12])}")
            spec["_heat_notes"] = notes

    heat_advise = bool(spec.get("heat_arc_advise") is True)
    audience_profile = None
    if isinstance(intent.get("audience_profile"), str):
        audience_profile = intent.get("audience_profile")
    elif isinstance(spec.get("audience_profile"), str):
        audience_profile = spec.get("audience_profile")
    coitus_grammar = (
        spec.get("coitus_grammar") if isinstance(spec.get("coitus_grammar"), dict) else None
    )
    # 卸装阶梯延续：前镜状态继承；衣服不回穿（lint HEAT_WARDROBE_RE_DRESS）
    wardrobe_cont = apply_wardrobe_continuity(shots, heat_scale=heat_scale)
    if (
        wardrobe_cont.get("filled_ids")
        or wardrobe_cont.get("bumped_ids")
        or wardrobe_cont.get("clamped_ids")
        or wardrobe_cont.get("escalated")
        or wardrobe_cont.get("start_pose_ids")
    ):
        notes = list(spec.get("_heat_notes") or [])
        bits = []
        if wardrobe_cont.get("filled_ids"):
            bits.append("wardrobe inherit: " + ",".join(wardrobe_cont["filled_ids"][:12]))
        if wardrobe_cont.get("bumped_ids"):
            bits.append("wardrobe undress-bump: " + ",".join(wardrobe_cont["bumped_ids"][:12]))
        if wardrobe_cont.get("clamped_ids"):
            bits.append("wardrobe re-dress CLAMPED: " + ",".join(wardrobe_cont["clamped_ids"][:12]))
        esc = wardrobe_cont.get("escalated") or []
        if esc:
            bits.append(
                "wardrobe IRON escalate: "
                + ",".join(
                    f"{e.get('id')}:{e.get('from')}→{e.get('to')}"
                    for e in esc[:12]
                    if isinstance(e, dict)
                )
            )
        if wardrobe_cont.get("start_pose_ids"):
            bits.append(
                "start_pose undress-lock: " + ",".join(wardrobe_cont["start_pose_ids"][:12])
            )
        notes.append("; ".join(bits))
        spec["_heat_notes"] = notes
    spec["_wardrobe_continuity"] = wardrobe_cont
    # spice_level default from heat/audience
    try:
        from edit_policy import HARDCORE_CRAFT_SPINE, normalize_spice_level
    except Exception:  # pragma: no cover  # noqa: BLE001
        normalize_spice_level = None  # type: ignore
        HARDCORE_CRAFT_SPINE = ()  # type: ignore
    spice_level = spec.get("spice_level")
    if normalize_spice_level is not None:
        resolved_spice = normalize_spice_level(
            spice_level, heat_scale=heat_scale, audience_profile=audience_profile
        )
        if resolved_spice and not spice_level:
            spec["spice_level"] = resolved_spice
            spice_level = resolved_spice
        elif spice_level:
            spice_level = str(spice_level).strip().lower()

    # Hardcore flat craft → inject montage spine (unless lock_craft)
    craft_raw = spec.get("edit_craft")
    craft_list: list[str] = []
    if isinstance(craft_raw, list):
        craft_list = [str(c) for c in craft_raw if str(c).strip()]
    elif isinstance(craft_raw, str) and craft_raw.strip():
        craft_list = [craft_raw.strip()]
    ap_l = str(audience_profile or "").strip().lower()
    hardcore_aud = ap_l in {"hardcore_male", "hardcore", "重口男向"}
    lock_craft = False
    es = spec.get("edit_strategy") if isinstance(spec.get("edit_strategy"), dict) else {}
    lock_craft = bool(es.get("lock_craft"))
    if (
        hardcore_aud
        and heat_scale == "max"
        and not lock_craft
        and (len(set(c.lower() for c in craft_list)) < 4 or not craft_list)
    ):
        n_join = max(1, len(shots) - 1)
        spine = list(HARDCORE_CRAFT_SPINE)
        while len(spine) < n_join:
            spine.extend(HARDCORE_CRAFT_SPINE)
        craft_list = spine[:n_join]
        spec["edit_craft"] = craft_list
        notes = list(spec.get("_heat_notes") or [])
        notes.append("hardcore edit_craft spine injected (montage/insert/smash)")
        spec["_heat_notes"] = notes

    # Prefer story-normalize raw for fidelity check when present on disk
    source_excerpt = (
        str(
            spec.get("source_script")
            or spec.get("source_excerpt")
            or (spec.get("_plan") or {}).get("raw_excerpt")
            or ""
        ).strip()
        or None
    )
    if film_root is not None and not source_excerpt:
        try:
            from pathlib import Path as _P

            norm_path = _P(film_root) / "receipts" / "story-normalize.json"
            if norm_path.is_file():
                import json as _json

                norm = _json.loads(norm_path.read_text(encoding="utf-8"))
                if isinstance(norm, dict):
                    source_excerpt = (
                        str(norm.get("raw_excerpt") or norm.get("logline") or "").strip() or None
                    )
        except Exception:  # noqa: BLE001
            source_excerpt = source_excerpt

    heat_rep = lint_heat_arc(
        shots,
        heat_scale=heat_scale,
        intimacy_min_ratio=spec.get("intimacy_min_ratio"),
        setup_max_ratio=spec.get("setup_max_ratio"),
        sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
        audience_profile=audience_profile,
        advise=heat_advise,
        coitus_grammar=coitus_grammar,
        spice_level=str(spice_level) if spice_level else None,
        edit_craft=craft_list or None,
        source_excerpt=source_excerpt,
    )
    spec["_heat_arc"] = heat_rep
    # max IRON: heat_arc_strict defaults true (intimacy ≥70% / setup ≤20%)
    heat_arc_strict = spec.get("heat_arc_strict")
    if heat_arc_strict is None:
        heat_arc_strict = heat_scale == "max" and spec.get("adult_max_iron") is not False
    arc_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "HEAT_INTIMACY_RATIO_LOW",
            "HEAT_SETUP_RATIO_HIGH",
            "HEAT_ACT_CLIMAX_EMPTY",
            "HEAT_ESCALATION_REGRESSION",
            "HEAT_ESCALATION_STALL",
            "HEAT_ESCALATION_NO_PEAK",
        }
    ]
    if heat_arc_strict is True and arc_fail_codes:
        raise FilmSpecError(
            "heat arc IRON failed (heat_arc_strict): "
            + ",".join(arc_fail_codes)
            + " — max: intimacy ≥60%, setup ≤20%, continuous challenge to climax bare "
            "(no mid-film cool-down / plateau). "
            "Override: heat_arc_strict:false or adult_max_iron:false."
        )
    # Explicit continuous-challenge flag (defaults with max iron)
    if spec.get("challenge_max_scale") is None and heat_scale == "max":
        if spec.get("adult_max_iron") is not False:
            spec["challenge_max_scale"] = True
    # P0 user-source fidelity only protects actual user source, never stock plans.
    fidelity_strict = spec.get("user_source_fidelity_strict")
    if fidelity_strict is None:
        fidelity_strict = heat_scale == "max" and bool(source_excerpt)
    if fidelity_strict is True and not source_excerpt:
        raise FilmSpecError(
            "user source fidelity requires source_excerpt when user_source_fidelity_strict=true"
        )
    fid_codes = [c for c in (heat_rep.get("codes") or []) if str(c).startswith("USER_SOURCE_")]
    if fidelity_strict is True and fid_codes:
        raise FilmSpecError(
            "user source fidelity failed (user_source_fidelity_strict): "
            + ",".join(fid_codes)
            + " — 用户原文被 adult-max 库存旁白覆盖。保留用户诗白/对白/专名；"
            "荤梗只可补后缀。See lessons-2026-07-22-user-source-fidelity.md"
        )
    # A1 · 2026-08-06: sex floor fail-closed (no silent duration pad) — plan/film_spec_sex_floor
    try:
        from plan.film_spec_sex_floor import (
            SexFloorError,
            apply_sex_duration_floor,
            resolve_sex_floor_strict,
        )
    except ImportError:  # pragma: no cover — flat scripts path
        from film_spec_sex_floor import (  # type: ignore
            SexFloorError,
            apply_sex_duration_floor,
            resolve_sex_floor_strict,
        )

    sex_floor_strict = resolve_sex_floor_strict(spec, heat_scale)
    try:
        apply_sex_duration_floor(
            heat_rep, sex_floor_strict=sex_floor_strict, heat_scale=heat_scale
        )
    except SexFloorError as exc:
        raise FilmSpecError(str(exc)) from exc
    # Sex wardrobe IRON: undress|bare + bare peak; continuity monotonic; hard on max.
    sex_wardrobe_strict = spec.get("sex_wardrobe_strict")
    if sex_wardrobe_strict is None:
        sex_wardrobe_strict = heat_scale == "max"
    wardrobe_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "HEAT_SEX_WARDROBE_DRESSED",
            "HEAT_SEX_WARDROBE_WEAK",
            "HEAT_UNDRESS_BEAT_MISSING",
            "HEAT_WARDROBE_RE_DRESS",
            "HEAT_WARDROBE_TEXT_CONFLICT",
            "HEAT_BARE_PEAK_MISSING",
        }
    ]
    if sex_wardrobe_strict is True and wardrobe_fail_codes:
        raise FilmSpecError(
            "sex wardrobe IRON failed (sex_wardrobe_strict): "
            + ",".join(wardrobe_fail_codes)
            + " — act≥undressed, climax=bare, undress beat required; "
            "能脱就脱/能露就露；禁止回穿。See lessons-2026-07-21-sex-undress-ladder.md"
        )
    # Peak still sole-ref: undressed/bare must not restart from full cast master
    still_src_strict = spec.get("still_source_strict")
    if still_src_strict is None:
        still_src_strict = heat_scale == "max" and spec.get("adult_max_iron") is not False
    if still_src_strict is True:
        try:
            from i2v_motion_gate import lint_still_source_policy
        except Exception:  # pragma: no cover  # noqa: BLE001
            lint_still_source_policy = None  # type: ignore
        if lint_still_source_policy is not None:
            still_rep = lint_still_source_policy(shots)
            spec["_still_source_policy"] = still_rep
            if not still_rep.get("ok"):
                raise FilmSpecError(
                    "still source wardrobe IRON failed (still_source_strict): "
                    + ",".join(still_rep.get("codes") or [])
                    + " — peak/undressed still sole-ref must be undress-anchor or prior "
                    "undressed still; 禁 image_edit(全装 cast)。"
                    " Override: still_source_strict:false."
                )
    # VO 荤梗：实打实办事剧，旁白全程要荤；act/climax 要办事动词
    sex_vo_strict = spec.get("sex_vo_strict")
    if sex_vo_strict is None:
        sex_vo_strict = heat_scale == "max"
    vo_fail_codes = [
        c
        for c in (heat_rep.get("codes") or [])
        if c
        in {
            "HEAT_VO_SPICE_MISSING",
            "HEAT_VO_SEX_VERB_WEAK",
            "HEAT_VO_SPICE_RATIO_LOW",
            "HEAT_VO_SPICE_TOO_MILD",
        }
    ]
    vo_mode_now = str(spec.get("vo_mode") or "").strip().lower()
    sex_vo_auto = spec.get("sex_vo_auto_apply")
    if sex_vo_auto is None:
        sex_vo_auto = vo_mode_now != "dialogue_drama"
    # Auto-reinforce weak nar only for storyteller/hybrid (never inject third-person into dialogue_drama)
    if (
        sex_vo_strict is True
        and vo_fail_codes
        and heat_scale == "max"
        and sex_vo_auto is not False
        and vo_mode_now != "dialogue_drama"
    ):
        try:
            from edit_policy import apply_vo_spice_auto

            vo_fix = apply_vo_spice_auto(
                shots, spice_level=str(spice_level) if spice_level else "extreme"
            )
        except Exception:  # pragma: no cover  # noqa: BLE001
            vo_fix = {"fixed": 0, "ids": []}
        if int(vo_fix.get("fixed") or 0) > 0:
            notes = list(spec.get("_heat_notes") or [])
            notes.append(
                f"sex_vo_auto_apply fixed {vo_fix['fixed']} shots: "
                + ",".join((vo_fix.get("ids") or [])[:8])
            )
            spec["_heat_notes"] = notes
            # re-lint heat after nar rewrite
            heat_rep = lint_heat_arc(
                shots,
                heat_scale=heat_scale,
                intimacy_min_ratio=spec.get("intimacy_min_ratio"),
                setup_max_ratio=spec.get("setup_max_ratio"),
                sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
                audience_profile=audience_profile,
                advise=heat_advise,
                coitus_grammar=coitus_grammar,
                spice_level=str(spice_level) if spice_level else None,
                edit_craft=craft_list or None,
                source_excerpt=source_excerpt,
            )
            spec["_heat_arc"] = heat_rep
            vo_fail_codes = [
                c
                for c in (heat_rep.get("codes") or [])
                if c
                in {
                    "HEAT_VO_SPICE_MISSING",
                    "HEAT_VO_SEX_VERB_WEAK",
                    "HEAT_VO_SPICE_RATIO_LOW",
                    "HEAT_VO_SPICE_TOO_MILD",
                }
            ]
    if sex_vo_strict is True and vo_fail_codes:
        raise FilmSpecError(
            "sex VO spice failed (sex_vo_strict): "
            + ",".join(vo_fail_codes)
            + " — every nar needs 荤梗; act/climax need 沉腰/办穿/吃进/锁腰/高潮… "
            "extreme 档禁纯双关。See lessons-2026-07-21-sex-vo-spice.md"
        )

    # Coitus six-beat + mute-frame pose (hard on max iron / hardcore / grammar)
    _hardcore_profiles = {"hardcore_male", "hardcore", "重口男向"}
    _max_iron = heat_scale == "max" and spec.get("adult_max_iron") is not False
    coitus_strict = spec.get("coitus_strict")
    if coitus_strict is None:
        ap = str(audience_profile or "").strip().lower()
        coitus_strict = (
            _max_iron
            or ap in _hardcore_profiles
            or bool((coitus_grammar or {}).get("enabled") is True)
        )
    _coitus_hard = {
        "COITUS_BEAT_MISSING",
        "COITUS_UNREADABLE_POSE",
        "COITUS_PSEUDO_SEX",
    }
    coitus_fail_codes = [
        str(i.get("code"))
        for i in (heat_rep.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code") or "") in _coitus_hard
        and str(i.get("severity") or "") == "warning"
    ]
    if coitus_strict is True and coitus_fail_codes:
        raise FilmSpecError(
            "coitus grammar failed (coitus_strict): "
            + ",".join(sorted(set(coitus_fail_codes)))
            + " — assign coitus_beat entry→hook; act stills must be coitus-readable "
            "(straddle/hips-sink/grind), not hug-only. See intercourse-impact-benchmark."
        )

    # 肉戏起承转合 (前戏→插入→射出) hard on max iron
    # P0 · 2026-07-29: SEX_ARC_RATIO_SKEW / RELEASE_RATIO_LOW also hard-fail
    sex_arc_strict = spec.get("sex_arc_strict")
    if sex_arc_strict is None:
        sex_arc_strict = _max_iron
    sex_arc_fail = [c for c in (heat_rep.get("codes") or []) if str(c).startswith("SEX_ARC_")]
    if sex_arc_strict is True and sex_arc_fail:
        raise FilmSpecError(
            "sex arc IRON failed (sex_arc_strict): "
            + ",".join(sex_arc_fail)
            + " — 前戏→插入→射出 must all exist with penetration verbs; "
            "转拍时长≥25% 肉戏窗、合拍≥12%。"
            "禁只抱吻、禁无纳入、禁无高潮射出拍。Override: sex_arc_strict:false. "
            "See lessons-2026-07-27-adult-scale-max-sex-arc.md"
        )

    # 定器特写 hard on max
    sex_detail_cu_strict = spec.get("sex_detail_cu_strict")
    if sex_detail_cu_strict is None:
        sex_detail_cu_strict = _max_iron
    if sex_detail_cu_strict is True and "SEX_DETAIL_CU_MISSING" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "sex detail CU IRON failed (sex_detail_cu_strict): SEX_DETAIL_CU_MISSING — "
            "肉戏块至少 1 镜结合/腰腹定器特写 (coverage_role=detail 或 "
            "framing=union_closeup|genital_lock 或 close-up insert). "
            "Override: sex_detail_cu_strict:false."
        )

    # 双方脱尽：warning codes only (UNSTATED is info)
    both_undress_strict = spec.get("both_undress_strict")
    if both_undress_strict is None:
        both_undress_strict = _max_iron
    if both_undress_strict is True and "SEX_BOTH_UNDRESS_MISSING" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "both undress IRON failed (both_undress_strict): SEX_BOTH_UNDRESS_MISSING — "
            "插入时女≥undressed/bare；partner_wardrobe_state 若填写则 ≥undressed。 "
            "Override: both_undress_strict:false."
        )

    size_ladder_strict = spec.get("size_ladder_strict")
    if size_ladder_strict is None:
        ap = str(audience_profile or "").strip().lower()
        size_ladder_strict = _max_iron or ap in _hardcore_profiles
    # Only warning-severity SIZE_* hard-fail (info stays advisory even when strict)
    size_fail_codes = [
        str(i.get("code"))
        for i in (heat_rep.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code") or "").startswith("SIZE_")
        and str(i.get("severity") or "") == "warning"
    ]
    if size_ladder_strict is True and size_fail_codes:
        raise FilmSpecError(
            "size ladder failed (size_ladder_strict): "
            + ",".join(sorted(set(size_fail_codes)))
            + " — vary WS→MS→CU→insert; do not reopen wide mid-act. "
            "See size-ladder-hardcore-stack."
        )

    montage_strict = spec.get("montage_strict")
    if montage_strict is None:
        ap = str(audience_profile or "").strip().lower()
        montage_strict = _max_iron or ap in _hardcore_profiles
    montage_fail = [
        str(i.get("code"))
        for i in (heat_rep.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code") or "").startswith("MONTAGE_")
        and str(i.get("severity") or "") == "warning"
    ]
    if montage_strict is True and montage_fail:
        raise FilmSpecError(
            "montage craft failed (montage_strict): "
            + ",".join(montage_fail)
            + " — need insert/smash/montage variety. See montage-hardcore-male."
        )

    pose_strict = spec.get("pose_strict")
    if pose_strict is None:
        ap = str(audience_profile or "").strip().lower()
        pose_strict = _max_iron or ap in _hardcore_profiles
    if pose_strict is True and "SEX_POSE_STALE" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "sex pose variety failed (pose_strict): SEX_POSE_STALE — "
            "rotate sex_pose across act shots (straddle/cowgirl/from_behind…)."
        )

    vo_motion_strict = spec.get("sex_vo_motion_strict")
    if vo_motion_strict is None:
        ap = str(audience_profile or "").strip().lower()
        vo_motion_strict = _max_iron or ap in _hardcore_profiles
    if vo_motion_strict is True and "HEAT_VO_MOTION_MISMATCH" in (heat_rep.get("codes") or []):
        raise FilmSpecError(
            "vo-motion align failed (sex_vo_motion_strict): HEAT_VO_MOTION_MISMATCH — "
            "mirror nar sex verbs in dsl.action/motion."
        )

    # Erotic impact scorecard — max IRON hard floor A (75) · 2026-07-29
    impact: dict[str, Any] | None = None
    with contextlib.suppress(Exception):
        impact = compute_erotic_impact_score(shots, heat_scale=heat_scale, heat_rep=heat_rep)
        spec["_erotic_impact"] = impact
    impact_strict = spec.get("erotic_impact_strict")
    if impact_strict is None:
        impact_strict = _max_iron
    impact_floor = float(spec.get("erotic_impact_floor") or 75.0)
    # Wave 4: always write heat-boost receipt when below S (agent loop)
    if impact is not None and heat_scale == "max" and film_root is not None:
        with contextlib.suppress(Exception):
            from pathlib import Path as _Path

            from edit_policy import suggest_impact_boost_actions
            from util import write_json as _write_json

            boost_plan = suggest_impact_boost_actions(
                shots,
                heat_scale=heat_scale,
                heat_rep=heat_rep,
                impact=impact,
                target_score=90.0,
            )
            rec_dir = _Path(film_root) / "receipts"
            rec_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                rec_dir / "heat-boost.json",
                {
                    "ok": True,
                    "kind": "heat-impact-boost",
                    "source": "write-spec",
                    "apply": False,
                    "heat_scale": heat_scale,
                    "plan": boost_plan,
                    "hint": "aifilm heat boost --root … --apply  # field patches toward S≥90",
                },
            )
            if boost_plan.get("needed"):
                notes = list(spec.get("_heat_notes") or [])
                notes.append(
                    f"heat-boost plan written (score={boost_plan.get('score')} "
                    f"gap={boost_plan.get('gap')} actions={len(boost_plan.get('actions') or [])}); "
                    "run heat boost --apply before bulk if below S"
                )
                spec["_heat_notes"] = notes
            # Optional auto field-patch (off by default)
            if (
                spec.get("auto_heat_boost") is True
                and boost_plan.get("needed")
                and float(impact.get("score") or 0) + 1e-9 < 90.0
            ):
                from edit_policy import apply_impact_boost_patches, apply_vo_spice_auto

                applied = apply_impact_boost_patches(shots, list(boost_plan.get("actions") or []))
                vo = apply_vo_spice_auto(shots, spice_level=str(spice_level or "extreme"))
                impact = compute_erotic_impact_score(
                    shots, heat_scale=heat_scale, heat_rep=heat_rep
                )
                spec["_erotic_impact"] = impact
                notes = list(spec.get("_heat_notes") or [])
                notes.append(
                    f"auto_heat_boost applied patches={applied.get('changed')} "
                    f"vo={vo.get('fixed')} → impact={impact.get('score')}"
                )
                spec["_heat_notes"] = notes
    if impact_strict is True and impact is not None:
        score = float(impact.get("score") or 0.0)
        if score + 1e-9 < impact_floor:
            raise FilmSpecError(
                f"erotic impact IRON failed (erotic_impact_strict): score={score} "
                f"< floor={impact_floor} (grade {impact.get('grade')}) — "
                "need sex≥50% + bare peak + 四拍弧 + 定器 CU + penetration verbs. "
                "Target grade A (≥75) / S (≥90). "
                "Run: aifilm heat boost --apply. "
                "Override: erotic_impact_strict:false or erotic_impact_floor."
            )

    # Heroine cast mode: single (default) vs multi — elastic from prompt/images/fields
    cast_ids: list[str] = []
    heroine_ids: list[str] = []
    raw_cast = intent.get("cast") if isinstance(intent.get("cast"), list) else None
    if raw_cast:
        cast_ids = [str(x).strip() for x in raw_cast if str(x).strip()]
    if isinstance(spec.get("cast_ids"), list):
        cast_ids = cast_ids or [str(x).strip() for x in spec["cast_ids"] if str(x).strip()]
    if isinstance(spec.get("heroine_ids"), list):
        heroine_ids = [str(x).strip() for x in spec["heroine_ids"] if str(x).strip()]
    elif isinstance(intent.get("heroines"), list):
        heroine_ids = [str(x).strip() for x in intent["heroines"] if str(x).strip()]

    cast_masters: dict[str, Any] = {}
    if isinstance(spec.get("cast_masters"), dict):
        cast_masters = dict(spec["cast_masters"])
    # optional style-bible path not always present; agent may put masters on spec

    # Female ref images: explicit list or count from user uploads
    female_ref_n: int | None = None
    if isinstance(spec.get("female_ref_image_count"), (int, float)):
        female_ref_n = int(spec["female_ref_image_count"])
    elif isinstance(spec.get("cast_ref_images"), list):
        female_ref_n = len([x for x in spec["cast_ref_images"] if x])
    elif isinstance(intent.get("cast_ref_images"), list):
        female_ref_n = len([x for x in intent["cast_ref_images"] if x])

    prompt_blob = " ".join(
        str(x or "")
        for x in (
            intent.get("tone"),
            intent.get("logline"),
            intent.get("theme"),
            spec.get("title"),
            spec.get("description"),
            spec.get("user_prompt"),
            spec.get("brief"),
        )
    )
    resolved = resolve_heroine_cast_mode(
        multi_heroine=spec.get("multi_heroine"),
        cast_mode=spec.get("cast_mode"),
        heroine_ids=heroine_ids,
        cast_ids=cast_ids,
        cast_masters=cast_masters,
        prompt_blob=prompt_blob,
        female_ref_image_count=female_ref_n,
    )
    # Persist resolved mode; do not invent multi_heroine when single
    # Keep cast_mode as resolved only if author used auto/omit
    author_mode = str(spec.get("cast_mode") or "auto").strip().lower()
    if author_mode in {"", "auto"}:
        spec["cast_mode"] = resolved["mode"]
    if resolved["active"]:
        if spec.get("multi_heroine") is None:
            spec["multi_heroine"] = True
        if resolved.get("heroine_ids") and not heroine_ids:
            spec["heroine_ids"] = list(resolved["heroine_ids"])
    # leave multi_heroine unset/false as author wrote — don't force false rewrite

    mh = lint_multi_heroine(
        shots,
        cast_ids=cast_ids,
        heroine_ids=list(resolved.get("heroine_ids") or heroine_ids),
        active=bool(resolved.get("active")),
        cast_mode=str(resolved.get("mode") or "single"),
    )
    mh = {
        **mh,
        "resolved": resolved,
        "cast_mode": resolved.get("mode"),
        "active": resolved.get("active"),
    }
    spec["_multi_heroine"] = mh
    notes = list(spec.get("_cast_mode_notes") or [])
    notes.append(f"cast_mode={resolved.get('mode')} reasons={resolved.get('reasons')}")
    spec["_cast_mode_notes"] = notes
    if spec.get("multi_heroine_strict") is True and mh["warning_count"] > 0:
        raise FilmSpecError(
            "multi-heroine lint failed (multi_heroine_strict): "
            + ",".join(mh["codes"] or ["MULTI"])
        )

    # Adult max has a separate sensory contract.  This is intentionally a
    # projection, not more prompt text: post/review can later bind it to media.
    try:
        from adult_max_director import apply_contract, validate_contract

        projection = apply_contract(spec, shots)
        sensory = validate_contract(spec, shots)
        spec["_adult_max_director"] = {**projection, **sensory}
        director = (
            spec.get("adult_max_director")
            if isinstance(spec.get("adult_max_director"), dict)
            else {}
        )
        if projection["active"] and director.get("strict", True) and not sensory["ok"]:
            raise FilmSpecError("adult max sensory contract failed: " + ",".join(sensory["codes"]))
    except ImportError:  # pragma: no cover - compatibility for partial installations
        pass

    return shots
