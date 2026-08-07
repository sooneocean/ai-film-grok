#!/usr/bin/env python3
"""Pre-final / pre-bulk health check from production lessons (Kei + 2026-07-17).

Hard fails block production claims; soft warnings are advisory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from production_gates import (
    ProductionGateError,
    anti_boring_variety_report,
    assert_face_identity_passed,
    headroom_report,
    load_pilot_approval,
    loop_risk_shots_from_spec,
    pilot_is_user_approved,
    style_bible_consistency_report,
    transition_export_readback_report,
    transition_policy_report,
)
from util import read_json, utc_now
from util.errors import FilmError

ECCHI_TONE = re.compile(
    r"色气|里番|同人|诱惑|后宫|sensual|ecchi|seductive|rnb|soul",
    re.I,
)


class PreflightError(FilmError):
    pass


from gates.preflight_issues import (
    _append_probe_error,
    _is_heat_max_iron,
    _issue,
)


def run_preflight(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    hard: list[dict[str, str]] = []
    soft: list[dict[str, str]] = []

    if not root.is_dir():
        raise PreflightError(f"film root missing: {root}")

    man = read_json(root / "manifest.json") or {}
    spec = read_json(root / "film-spec.json") or {}
    style = read_json(root / "style-bible.json") or {}
    pilot = load_pilot_approval(root)
    score = read_json(root / "receipts" / "pilot-scorecard.json") or {}

    post_plan_path = root / "post-plan.json"
    if post_plan_path.is_file():
        try:
            from post_plan import PostPlanError, load_post_plan

            post_plan = load_post_plan(root, required=True)
            outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
            final = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
            final_engine = final.get("post_engine") if isinstance(final, dict) else None
            if final_engine and final_engine != post_plan["post_owner"]:
                hard.append(
                    _issue(
                        "hard",
                        "post_owner_mismatch",
                        f"post-plan owner={post_plan['post_owner']} but final_film post_engine={final_engine}",
                        fix="重新以 post-plan owner 渲染/注册 final；勿把 comparison 或 FFmpeg final 记成该 owner",
                    )
                )
        except (PostPlanError, OSError) as exc:
            hard.append(
                _issue(
                    "hard",
                    "post_plan_invalid",
                    f"post-plan 无法验证: {exc}",
                    fix=f'aifilm post-plan --root "{root}" validate',
                )
            )

    # Premium vertical is an authored creative contract, not a styling hint.
    # Keep standard/legacy roots compatible while failing closed before paid work.
    book = read_json(root / "production-book.json") or {}
    if isinstance(book, dict) and book.get("quality_target", "standard") == "premium_vertical":
        try:
            from creative_quality import validate_premium_vertical

            creative = validate_premium_vertical(root)
            for issue in creative.get("errors") or []:
                hard.append(
                    _issue(
                        "hard",
                        str(issue.get("code") or "CREATIVE_QUALITY_MISSING"),
                        str(issue.get("message") or "premium creative contract failed"),
                        fix="aifilm plan edit/graph project/write-spec 后重新运行 preflight",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            hard.append(_issue("hard", "CREATIVE_QUALITY_VALIDATION_FAILED", str(exc)[:200]))
        try:
            from creative_pipeline import preproduction_readiness

            readiness = preproduction_readiness(root, write=True)
            for blocker in readiness.get("blockers") or []:
                hard.append(
                    _issue(
                        "hard",
                        str(blocker.get("code") or "PREPRODUCTION_NOT_READY"),
                        str(blocker.get("message") or "premium pre-production gate failed"),
                        fix="完成 Radio Cut 与 Animatic 人审回执后重新运行 preflight",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            hard.append(_issue("hard", "PREPRODUCTION_READINESS_FAILED", str(exc)[:200]))

    # --- structure ---
    if not man:
        hard.append(_issue("hard", "no_manifest", "missing manifest.json", fix="aifilm init …"))
    if not spec:
        hard.append(
            _issue("hard", "no_spec", "missing film-spec.json", fix="aifilm write-spec --root …")
        )

    graph_path = root / "drama-graph.json"
    if graph_path.is_file():
        try:
            from narrative_control import validate_narrative_graph

            narrative = validate_narrative_graph(read_json(graph_path) or {}, strict=True)
            for issue in narrative.get("errors") or []:
                hard.append(
                    _issue(
                        "hard",
                        str(issue.get("code") or "NARRATIVE_INVALID"),
                        str(issue.get("message") or "narrative contract failed"),
                        fix='aifilm plan edit --root "<root>" then plan validate --strict',
                    )
                )
        except Exception as exc:  # noqa: BLE001
            hard.append(_issue("hard", "NARRATIVE_VALIDATION_FAILED", str(exc)[:200]))
    if style.get("state") != "Approved" and not style.get("locked"):
        soft.append(
            _issue(
                "soft",
                "style_not_approved",
                f"Visual Bible state is {style.get('state', 'Unknown')} (unlocked), expected Approved",
                fix="aifilm bible lock --root …",
            )
        )

    # --- Framing iron: full head + headroom is a hard delivery gate. ---
    # Never validate_film_spec() on live `spec` — it mutates sound_plan/coverage in place.
    if spec:
        try:
            import copy

            from film_spec import validate_film_spec
            from framing_lint import lint_framing_iron

            shots_for_frame: list = []
            try:
                shots_for_frame = validate_film_spec(copy.deepcopy(spec), assign_missing_ids=False)
            except Exception:
                for scene in spec.get("scenes") or []:
                    if not isinstance(scene, dict):
                        continue
                    for sh in scene.get("shots") or []:
                        if isinstance(sh, dict):
                            shots_for_frame.append(sh)
            if shots_for_frame:
                frm = lint_framing_iron(shots_for_frame)
                if not frm.get("ok"):
                    codes = ",".join(frm.get("codes") or ["FRAMING"])
                    issue = _issue(
                        "hard",
                        "framing_crop_prone",
                        f"framing crop-prone language: {codes} — "
                        f"{(frm.get('issues') or [{}])[0].get('message', '')[:160]}",
                        fix="改 framing/motion：每个主角完整头部 + 头顶留白；空间不足时裁脚，不得裁头",
                    )
                    hard.append(issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "framing_probe_error",
                    f"framing lint probe failed: {exc}"[:200],
                    fix="check framing_lint.py",
                )
            )

    # --- VO / loop (Kei) + TTS rehearsal measured timing ---
    tts_timing: dict[str, Any] | None = None
    if spec:
        # Prefer measured_duration_sec from receipts/tts-rehearsal.json when present
        measured_map: dict[str, float] = {}
        try:
            from tts_rehearsal import bind_receipt_to_spec_timing, measured_vo_by_shot

            measured_map = measured_vo_by_shot(root)
            strict_reh = bool(spec.get("tts_rehearsal_required") is True) or (
                os.environ.get("AIFILM_STRICT_TTS_REHEARSAL", "").strip().lower()
                in {"1", "true", "yes"}
            )
            tts_timing = bind_receipt_to_spec_timing(root, strict=strict_reh, raise_on_fail=False)
            if strict_reh and not tts_timing.get("present"):
                hard.append(
                    _issue(
                        "hard",
                        "tts_rehearsal_required",
                        "tts_rehearsal_required but missing receipts/tts-rehearsal.json",
                        fix='aifilm tts-rehearse --root "<root>"（可 --register-json 离线）',
                    )
                )
            over_m = list(tts_timing.get("over_plate_shots") or [])
            if over_m:
                hard.append(
                    _issue(
                        "hard",
                        "tts_rehearsal_over_plate",
                        (
                            f"measured VO exceeds plate on {over_m} "
                            "(vo_pacing uses measured_duration_sec when receipt present)"
                        ),
                        fix="拆 nar / 升 duration_sec / 重 tts-rehearse；勿指望 final loop",
                    )
                )
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "tts_rehearsal_probe_error",
                    f"tts rehearsal timing probe failed: {exc}"[:200],
                    fix="check receipts/tts-rehearsal.json / tts_rehearsal.py",
                )
            )

        try:
            risk = loop_risk_shots_from_spec(spec, measured_by_shot=measured_map or None, root=root)
        except Exception as exc:
            risk = []
            _append_probe_error(
                hard,
                soft,
                code="loop_risk_probe_error",
                exc=exc,
                fix="check production_gates.loop_risk_shots_from_spec / tts-rehearsal",
            )
        if risk:
            hard.append(
                _issue(
                    "hard",
                    "loop_risk",
                    f"loop_risk_shots={risk} — VO too long for plate; will force stream_loop"
                    + (" (measured preferred)" if measured_map else " (estimate)"),
                    fix="拆 nar / 升 duration_sec=10 / 加镜；勿指望 final loop",
                )
            )
        budget = spec.get("_vo_budget") if isinstance(spec.get("_vo_budget"), dict) else {}
        over_rec = budget.get("shots_over_recommended") or []
        if over_rec:
            soft.append(
                _issue(
                    "soft",
                    "nar_over_recommended",
                    f"shots over recommended nar length: {over_rec}",
                    fix="快节奏建议每镜 nar ≤28 字",
                )
            )

        # --- VO drag risk (星声·谢幕后 2026-07-20): short VO + long plate ---
        # If agent forces visual_fit:slot to hit 60s while nar is short, speech used to
        # be slowed (atempo≪1) and felt 卡. Code now pads; still soft-warn dead-air risk.
        try:
            drag_shots: list[str] = []
            try:
                from edit_policy import default_visual_fit

                global_fit = (
                    str(spec.get("visual_fit") or default_visual_fit(spec) or "slot")
                    .strip()
                    .lower()
                )
            except Exception:
                global_fit = str(spec.get("visual_fit") or "slot").strip().lower()
            for scene in spec.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                for sh in scene.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    sid = str(sh.get("id") or "")
                    shot_fit = str(sh.get("visual_fit") or "").strip().lower()
                    use_fit = shot_fit if shot_fit in {"vo", "slot"} else global_fit
                    if use_fit != "slot":
                        continue
                    plate = float(sh.get("duration_sec") or 6.0)
                    if plate <= 0:
                        continue
                    vo_m = measured_map.get(sid) if measured_map else None
                    if vo_m is None:
                        # crude estimate ~4 chars/sec Chinese storyteller
                        nar = str(sh.get("nar") or "")
                        vo_m = max(0.5, len(nar) / 4.0)
                    ratio = float(vo_m) / plate
                    if ratio < 0.92:
                        drag_shots.append(f"{sid}(vo/plate={ratio:.2f})")
            if drag_shots:
                soft.append(
                    _issue(
                        "soft",
                        "VO_DRAG_OR_DEAD_AIR",
                        (
                            f"short VO vs long plate on {drag_shots[:8]}"
                            + ("…" if len(drag_shots) > 8 else "")
                            + " — speech will pad (not slow); risk of dead air / thin 60s fill"
                        ),
                        fix=(
                            "prefer visual_fit:vo for snappy shorts; or lengthen nar / add shots "
                            "for full 60s; do NOT force atempo≪1. See lessons-2026-07-20-vo-drag-motion-snap.md"
                        ),
                    )
                )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="vo_drag_probe_error",
                exc=exc,
                fix="check edit_policy.default_visual_fit / VO drag preflight block",
            )

        # --- Equal-slot PPT risk (Wave γ · 2026-08-04) ---
        try:
            from edit_policy import default_visual_fit, lint_equal_duration_ppt

            fit = str(spec.get("visual_fit") or default_visual_fit(spec) or "slot").strip().lower()
            flat: list[dict[str, Any]] = []
            for scene in spec.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict):
                        flat.append(sh)
            ppt = lint_equal_duration_ppt(flat, visual_fit=fit)
            if not ppt.get("ok"):
                soft.append(
                    _issue(
                        "soft",
                        "EQUAL_SLOT_PPT_RISK",
                        "; ".join(
                            str(i.get("message") or i.get("code"))
                            for i in (ppt.get("issues") or [])
                        ),
                        fix="set visual_fit:vo (dialogue_drama default) or vary duration_sec / re-I2V",
                    )
                )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="equal_slot_ppt_probe_error",
                exc=exc,
                fix="check edit_policy.lint_equal_duration_ppt",
            )

        # --- Sex duration floor (性爱片段 act+climax ≥20% plate · 2026-07-21) ---
        try:
            heat_rep = spec.get("_heat_arc") if isinstance(spec.get("_heat_arc"), dict) else None
            if heat_rep is None:
                from edit_policy import lint_heat_arc

                heat_shots: list = []
                for scene in spec.get("scenes") or []:
                    if not isinstance(scene, dict):
                        continue
                    for sh in scene.get("shots") or []:
                        if isinstance(sh, dict):
                            heat_shots.append(sh)
                intent = (
                    spec.get("director_intent")
                    if isinstance(spec.get("director_intent"), dict)
                    else {}
                )
                heat_rep = lint_heat_arc(
                    heat_shots,
                    heat_scale=spec.get("heat_scale"),
                    sex_min_duration_ratio=spec.get("sex_min_duration_ratio"),
                    audience_profile=intent.get("audience_profile") or spec.get("audience_profile"),
                )
            heat_codes = list(heat_rep.get("codes") or [])
            if "HEAT_SEX_DURATION_LOW" in heat_codes:
                soft.append(
                    _issue(
                        "soft",
                        "HEAT_SEX_DURATION_LOW",
                        (
                            f"性爱片段(act+climax) duration "
                            f"{heat_rep.get('sex_duration_ratio')} "
                            f"({heat_rep.get('sex_duration_sec')}s/"
                            f"{heat_rep.get('total_duration_sec')}s) "
                            f"< floor {heat_rep.get('sex_duration_floor')} "
                            f"— heat_scale={heat_rep.get('heat_scale')}"
                        ),
                        fix=(
                            "add/lengthen heat_phase=act|climax plates until ≥20% total "
                            "duration_sec (hardcore_male target 40%); "
                            "write-spec hard when heat_scale=max unless sex_floor_strict:false. "
                            "See references/ecchi-story.md · lessons-2026-07-21-sex-duration-floor.md"
                        ),
                    )
                )
            for wcode in (
                "HEAT_SEX_WARDROBE_DRESSED",
                "HEAT_SEX_WARDROBE_WEAK",
                "HEAT_UNDRESS_BEAT_MISSING",
                "HEAT_WARDROBE_RE_DRESS",
                "HEAT_WARDROBE_TEXT_CONFLICT",
            ):
                if wcode in heat_codes:
                    soft.append(
                        _issue(
                            "soft",
                            wcode,
                            (
                                f"sex wardrobe ladder: {wcode} — "
                                f"dressed={((heat_rep.get('wardrobe') or {}).get('dressed_sex_shots'))} "
                                f"undress_beats={((heat_rep.get('wardrobe') or {}).get('undress_beats'))} "
                                f"re_dress={((heat_rep.get('wardrobe') or {}).get('re_dress_shots'))} "
                                f"text_conflict={((heat_rep.get('wardrobe') or {}).get('text_conflict_shots'))} "
                                f"peak={((heat_rep.get('wardrobe') or {}).get('peak_state'))}"
                            ),
                            fix=(
                                "act/climax: wardrobe_state=partial|undressed|bare; "
                                "add foreplay undress action (removes armor / 卸甲 / 脱下); "
                                "still/I2V must show armor/clothes off; "
                                "后镜延续前镜卸装、禁止回穿 (rank only rises); "
                                "下一镜 start_pose/subject 从已脱状态开场，禁 full wardrobe。 "
                                "See lessons-2026-07-21-sex-undress-ladder.md"
                            ),
                        )
                    )
            for vcode in (
                "HEAT_VO_SPICE_MISSING",
                "HEAT_VO_SEX_VERB_WEAK",
                "HEAT_VO_SPICE_RATIO_LOW",
            ):
                if vcode in heat_codes:
                    soft.append(
                        _issue(
                            "soft",
                            vcode,
                            (
                                f"VO 荤梗: {vcode} — "
                                f"bland={((heat_rep.get('vo_spice') or {}).get('bland_shots'))} "
                                f"weak_sex={((heat_rep.get('vo_spice') or {}).get('weak_sex_vo_shots'))} "
                                f"spice_ratio={((heat_rep.get('vo_spice') or {}).get('spice_ratio'))}"
                            ),
                            fix=(
                                "rewrite every nar with 荤梗; act/climax use 沉腰/办穿/吃进/锁腰/高潮/换你顶; "
                                "ban pure literary 灯灭/回眸. lessons-2026-07-21-sex-vo-spice.md"
                            ),
                        )
                    )
            if str(spec.get("heat_scale") or "").lower() == "max":
                # Surface metrics even when pass (agent can see ratio)
                sdr = heat_rep.get("sex_duration_ratio")
                if sdr is not None and float(sdr) + 1e-9 < 0.35:
                    soft.append(
                        _issue(
                            "soft",
                            "HEAT_SEX_DURATION_ADVISORY",
                            (
                                f"sex duration {sdr} is above floor but below advisory 0.35 "
                                f"({heat_rep.get('sex_duration_sec')}s/"
                                f"{heat_rep.get('total_duration_sec')}s act+climax)"
                            ),
                            fix=(
                                "for 大尺度 adult max, aim act+climax ≥35% duration; "
                                "hardcore_male ≥40%. See ecchi-story.md"
                            ),
                        )
                    )
                # Wave 4: max IRON — duration/wardrobe/arc codes hard-block preflight
                max_hard_codes = {
                    "HEAT_SEX_DURATION_LOW",
                    "HEAT_SEX_WARDROBE_DRESSED",
                    "HEAT_BARE_PEAK_MISSING",
                    "HEAT_WARDROBE_RE_DRESS",
                    "SEX_ARC_FOREPLAY_MISSING",
                    "SEX_ARC_PENETRATION_MISSING",
                    "SEX_ARC_CLIMAX_RELEASE_MISSING",
                    "SEX_ARC_HUG_AS_SEX",
                    "SEX_DETAIL_CU_MISSING",
                }
                for code in max_hard_codes:
                    if code in heat_codes and spec.get("adult_max_iron") is not False:
                        hard.append(
                            _issue(
                                "hard",
                                code,
                                f"adult max IRON preflight: {code}",
                                fix=(
                                    f'aifilm heat boost --root "{root}" --apply && '
                                    f'aifilm heat check --root "{root}"'
                                ),
                            )
                        )
                # Erotic impact A floor
                impact = (
                    spec.get("_erotic_impact")
                    if isinstance(spec.get("_erotic_impact"), dict)
                    else {}
                )
                score = impact.get("score")
                floor = float(spec.get("erotic_impact_floor") or 75.0)
                if (
                    score is not None
                    and spec.get("erotic_impact_strict") is not False
                    and spec.get("adult_max_iron") is not False
                    and float(score) + 1e-9 < floor
                ):
                    hard.append(
                        _issue(
                            "hard",
                            "EROTIC_IMPACT_BELOW_A",
                            f"erotic impact {score} < A floor {floor} (grade {impact.get('grade')})",
                            fix=f'aifilm heat boost --root "{root}" --apply  # target S≥90',
                        )
                    )
                elif score is not None and float(score) + 1e-9 < 90.0:
                    soft.append(
                        _issue(
                            "soft",
                            "EROTIC_IMPACT_BELOW_S",
                            f"erotic impact {score} < S target 90 (grade {impact.get('grade')})",
                            fix=f'aifilm heat boost --root "{root}" --apply',
                        )
                    )
        except Exception as exc:
            # A1 · heat/erotic impact probe must not silent-green under adult max IRON
            _append_probe_error(
                hard,
                soft,
                code="heat_arc_probe_error",
                exc=exc,
                fix="check edit_policy.lint_heat_arc / _heat_arc / erotic impact",
                hard_mode=_is_heat_max_iron(spec),
            )

        # --- Character stance / multi-POV (角色立场 · 2026-07-20) ---
        try:
            from edit_policy import lint_character_stance

            stance_shots: list = []
            for scene in spec.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict):
                        stance_shots.append(sh)
            # Prefer write-spec report if present
            report = (
                spec.get("_character_stance")
                if isinstance(spec.get("_character_stance"), dict)
                else None
            )
            if report and report.get("codes"):
                codes = list(report.get("codes") or [])
            else:
                codes = list((lint_character_stance(stance_shots) or {}).get("codes") or [])
            if codes:
                soft.append(
                    _issue(
                        "soft",
                        "CHARACTER_STANCE",
                        f"multi-POV / stance soft lint: {codes}",
                        fix=(
                            "fill dsl.focal_character + viewpoint + look_axis; "
                            "rotate ots/reverse/reaction; flip focal on reverse. "
                            "See references/character-stance.md"
                        ),
                    )
                )
            # Missing stance fields on ≥4-shot films
            if len(stance_shots) >= 4:
                missing_vp = 0
                for sh in stance_shots:
                    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                    if not (dsl.get("viewpoint") or sh.get("viewpoint")):
                        missing_vp += 1
                if missing_vp >= max(2, len(stance_shots) // 2):
                    soft.append(
                        _issue(
                            "soft",
                            "STANCE_FIELDS_SPARSE",
                            f"{missing_vp}/{len(stance_shots)} shots missing dsl.viewpoint",
                            fix="run write-spec to inject stance, or set viewpoint/focal_character by hand",
                        )
                    )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="character_stance_probe_error",
                exc=exc,
                fix="check edit_policy.lint_character_stance",
            )

        tts = str(spec.get("tts_backend") or "auto").lower()
        vo_voice = str(spec.get("vo_voice") or "").strip()
        # Phase E hard: Edge Neural voice + external/ElevenLabs is a hard fail
        try:
            from tts_backend import assert_voice_backend_compatible  # type: ignore

            check_voice = vo_voice or "zh-CN-XiaoxiaoNeural"
            try:
                assert_voice_backend_compatible(tts, check_voice)
            except Exception as tts_exc:
                hard.append(
                    _issue(
                        "hard",
                        "tts_neural_on_external",
                        str(tts_exc)[:280],
                        fix="final --tts-backend edge（中文旁白）；或把 vo_voice 改成 provider voice id",
                    )
                )
        except ImportError:
            pass
        if tts in {"auto", "external"} or os.environ.get("AIFILM_TTS_ARGV"):
            soft.append(
                _issue(
                    "soft",
                    "tts_external_risk",
                    f"tts_backend={tts!r} or AIFILM_TTS_ARGV set — 中文 Neural ID 勿塞 ElevenLabs",
                    fix="final 时显式 --tts-backend edge（中文说书默认）；本机克隆用 voicebox",
                )
            )
        # 说书人优先 MiMo；其他显式 provider 仍允许，但保留可见提示。
        vo_mode = str(spec.get("vo_mode") or "").lower()
        if vo_mode in {"storyteller", "hybrid"} and tts not in {"mimo", "edge", ""}:
            soft.append(
                _issue(
                    "soft",
                    "tts_storyteller_not_mimo",
                    f"vo_mode={vo_mode} 但 tts_backend={tts!r} — 中文说书默认 MiMo",
                    fix="write-spec 会按声线政策解析 auto；或 final --tts-backend edge",
                )
            )
        if tts == "voicebox":
            try:
                from tts_backend import probe_voicebox  # type: ignore

                vb = probe_voicebox()
            except Exception as exc:  # pragma: no cover
                vb = {"ok": False, "error": str(exc)}
            if not vb.get("ok"):
                soft.append(
                    _issue(
                        "soft",
                        "tts_voicebox_not_ready",
                        f"tts_backend=voicebox but local studio not ready: {vb.get('error') or 'unknown'}",
                        fix="启动 Voicebox App；设 VOICEBOX_PROFILE；或改 tts_backend=mimo",
                    )
                )

        # BGM mood
        tone = ""
        intent = (
            spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
        )
        tone = str(intent.get("tone") or "") + " " + str(spec.get("title") or "")
        sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
        mood = str(sp.get("mood") or "").lower()
        if ECCHI_TONE.search(tone) and mood in {"dark", "horror"}:
            hard.append(
                _issue(
                    "hard",
                    "ecchi_dark_bgm",
                    f"色气 tone 却 sound_plan.mood={mood!r}（恐怖感）",
                    fix="改 sound_plan.mood 为 rnb/soul/sensual；horror 才用 dark",
                )
            )
        elif (
            ECCHI_TONE.search(tone)
            and mood
            and mood not in {"rnb", "soul", "sensual", "seductive", "warm", "playful", ""}
        ):
            soft.append(
                _issue(
                    "soft",
                    "ecchi_mood_check",
                    f"色气片 mood={mood!r} — 默认应用 rnb",
                    fix="sound_plan.mood: rnb",
                )
            )
        elif ECCHI_TONE.search(tone) and not mood:
            soft.append(
                _issue(
                    "soft",
                    "ecchi_mood_default",
                    "色气 tone 未写 sound_plan.mood — final 默认 rnb",
                    fix="建议 film-spec 写 sound_plan.mood: rnb",
                )
            )

        # VO–motion link / anti-fatigue (lessons-2026-07-17-vo-motion-link)
        vml = spec.get("_vo_motion_link") if isinstance(spec.get("_vo_motion_link"), dict) else {}
        vml_codes = list(vml.get("codes") or [])
        if not vml_codes:
            # Live re-lint if write-spec not re-run after skill patch
            shots: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots.extend(sc["shots"])
            if shots:
                try:
                    from continuity import lint_vo_motion_link

                    live = lint_vo_motion_link(
                        shots,
                        transition_intents=spec.get("transition_intents")
                        if isinstance(spec.get("transition_intents"), list)
                        else None,
                    )
                    vml_codes = list(live.get("codes") or [])
                    vml = live
                except Exception as exc:
                    _append_probe_error(
                        hard,
                        soft,
                        code="vo_motion_link_probe_error",
                        exc=exc,
                        fix="check continuity.lint_vo_motion_link",
                    )
        if vml_codes:
            soft.append(
                _issue(
                    "soft",
                    "vo_motion_link",
                    f"口白·动作/防腻 soft lint: {vml_codes} (warn={vml.get('warning_count')})",
                    fix=(
                        "每镜 nar 的动词=action 主动词=motion 首要运动；"
                        "hook/approach/action 禁止只有 blink/breath/push-in；"
                        "连续 3 镜换景别/机位/主动词；见 lessons-2026-07-17-vo-motion-link.md"
                    ),
                )
            )

        # Frame chain (lessons-2026-07-20-frame-chain) — soft/hold need end_pose→start_pose
        fch = spec.get("_frame_chain") if isinstance(spec.get("_frame_chain"), dict) else {}
        fch_codes = list(fch.get("codes") or [])
        if not fch_codes:
            shots_fc: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_fc.extend(sc["shots"])
            if shots_fc:
                try:
                    from continuity import lint_frame_chain

                    live_fc = lint_frame_chain(
                        shots_fc,
                        transition_intents=spec.get("transition_intents")
                        if isinstance(spec.get("transition_intents"), list)
                        else None,
                    )
                    fch_codes = list(live_fc.get("codes") or [])
                    fch = live_fc
                except Exception as exc:
                    _append_probe_error(
                        hard,
                        soft,
                        code="frame_chain_probe_error",
                        exc=exc,
                        fix="check continuity.lint_frame_chain",
                    )
        if fch_codes:
            soft.append(
                _issue(
                    "soft",
                    "frame_chain",
                    f"镜间动作串接 soft lint: {fch_codes} (warn={fch.get('warning_count')})",
                    fix=(
                        "soft/hold 写 end_pose→start_pose；continue 缝 "
                        "`extract-frame --promote-keyframe <next>` 逐字节复用末帧为下镜 keyframe；"
                        "禁止从 cast 重起。禁止 dissolve/定格/倒放/无关插镜掩盖。见 continuity_chain.md"
                    ),
                )
            )

        # Meaningful motion (story-bearing dynamics)
        mm = (
            spec.get("_meaningful_motion")
            if isinstance(spec.get("_meaningful_motion"), dict)
            else {}
        )
        mm_codes = list(mm.get("codes") or [])
        if not mm_codes:
            shots_mm: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_mm.extend(sc["shots"])
            if shots_mm:
                try:
                    from continuity import lint_meaningful_motion

                    live_mm = lint_meaningful_motion(shots_mm)
                    mm_codes = list(live_mm.get("codes") or [])
                    mm = live_mm
                except Exception as exc:
                    _append_probe_error(
                        hard,
                        soft,
                        code="meaningful_motion_probe_error",
                        exc=exc,
                        fix="check continuity.lint_meaningful_motion",
                        hard_mode=spec.get("meaningful_motion_strict") is True,
                    )
        if mm_codes:
            mm_strict = spec.get("meaningful_motion_strict") is True
            mm_msg = (
                f"动态叙事意涵 {'hard' if mm_strict else 'soft'} lint: {mm_codes} "
                f"(warn={mm.get('warning_count')})"
            )
            mm_fix = (
                "每镜 motion 须回答 beat 故事问题（登场/靠近/感官/反应/行动/余韵）；"
                "写 dsl.visible_change + 主动词领先；禁止只有 blink/push-in 氛围。"
                "见 lessons-2026-07-20-meaningful-motion.md"
            )
            mm_issue = _issue(
                "hard" if mm_strict else "soft",
                "meaningful_motion",
                mm_msg,
                fix=mm_fix,
            )
            if mm_strict:
                hard.append(mm_issue)
            else:
                soft.append(mm_issue)

        # --- Anti-boring variety (shot-variety-anti-boring P0) ---
        # Hard when anti_boring_strict; otherwise soft advisory so authors see variety debt.
        try:
            abr = anti_boring_variety_report(spec)
            ab_codes = list(abr.get("codes") or [])
            if ab_codes:
                ab_strict = spec.get("anti_boring_strict") is True
                ab_issue = _issue(
                    "hard" if ab_strict else "soft",
                    "anti_boring_variety",
                    f"anti-boring variety {'hard' if ab_strict else 'soft'}: {ab_codes} "
                    f"— {(abr.get('issues') or [{}])[0].get('message', '')[:120]}",
                    fix=(
                        "每镜一运动语言(禁相邻同 dsl.motion)；景别每 ≤2 镜一变(禁连续≥3镜同 size)；"
                        "主戏镜 duration_sec ≥4.5s；shot_size 三处同值。见 "
                        "lessons-2026-07-29-shot-variety-anti-boring.md"
                    ),
                )
                if ab_strict:
                    hard.append(ab_issue)
                else:
                    soft.append(ab_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "anti_boring_probe_error",
                    f"anti-boring probe failed: {exc}"[:200],
                    fix="check production_gates.anti_boring_variety_report",
                )
            )

        # --- Face-identity post_audit (face-identity-pixel P0) ---
        # Proven drift always hard; enroll/audit gaps default HARD (lock-face necessary).
        # Legacy soft: film-spec face_identity_soft=true.
        try:
            fi_report = assert_face_identity_passed(root, force=False, env_skip=False)
            if fi_report.get("skipped") is True:
                pass
            elif not fi_report.get("ok"):
                hard.append(
                    _issue(
                        "hard",
                        "face_identity_gate",
                        f"face-identity gate: {fi_report.get('codes')} — "
                        f"{(fi_report.get('issues') or [{}])[0].get('message','')[:120]}",
                        fix=(
                            "aifilm face-identity enroll-bible && aifilm face-identity audit --root "
                            f'"{root}"（漂移 keyframe 重拍/重编辑后再批准）'
                        ),
                    )
                )
            elif fi_report.get("soft"):
                soft.append(
                    _issue(
                        "soft",
                        "face_identity_gate",
                        f"face-identity advisory: {fi_report.get('codes')} — "
                        f"{(fi_report.get('issues') or [{}])[0].get('message','')[:120]}",
                        fix=(
                            "aifilm face-identity enroll-bible && aifilm face-identity audit --root "
                            f'"{root}"'
                        ),
                    )
                )
        except ProductionGateError as exc:
            hard.append(
                _issue(
                    "hard",
                    "face_identity_gate",
                    f"face-identity gate: {str(exc)[:200]}",
                    fix=(
                        "aifilm face-identity enroll-bible && aifilm face-identity audit --root "
                        f'"{root}"（漂移 keyframe 重拍/重编辑后再批准）'
                    ),
                )
            )
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "face_identity_probe_error",
                    f"face-identity probe failed: {exc}"[:200],
                    fix="check production_gates.assert_face_identity_passed",
                )
            )

        # --- Headroom / anti-crop (shortform headroom P1) ---
        # Timeline half of "防裁头": every shot >= 2.0s, scene-openers >= 3.5s lead-in.
        # Soft advisory by default; hard on headroom_strict or adult max heat.
        try:
            hr = headroom_report(spec)
            hr_codes = list(hr.get("codes") or [])
            if hr_codes:
                hr_strict = spec.get("headroom_strict") is True or str(
                    spec.get("heat_scale") or ""
                ).lower() in {"max", "hot", "extreme"}
                hr_issue = _issue(
                    "hard" if hr_strict else "soft",
                    "headroom_protect",
                    f"headroom {'hard' if hr_strict else 'soft'}: {hr_codes} — "
                    f"{(hr.get('issues') or [{}])[0].get('message', '')[:120]}",
                    fix=(
                        "每镜 duration_sec ≥2.0s；场景开头镜 ≥3.5s 留白，避免裁头/ abrupt cut。"
                        "lessons-2026-08-06-headroom"
                    ),
                )
                if hr_strict:
                    hard.append(hr_issue)
                else:
                    soft.append(hr_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "headroom_probe_error",
                    f"headroom probe failed: {exc}"[:200],
                    fix="check production_gates.headroom_report",
                )
            )

        # --- Controlled transition policy (HF 转场受控) ---
        # Default HARD; legacy soft only when transition_policy_soft=true.
        # Continue-seam violations always hard (接戏铁律).
        try:
            tp = transition_policy_report(spec)
            tp_codes = list(tp.get("codes") or [])
            if tp_codes:
                tp_soft = spec.get("transition_policy_soft") is True
                continue_hard = "HF_TRANSITION_CONTINUE_NOT_HARD" in tp_codes
                tp_hard = (not tp_soft) or continue_hard
                # When soft mode, only continue codes go hard; others soft.
                if tp_soft and not continue_hard:
                    severity = "soft"
                else:
                    severity = "hard" if tp_hard else "soft"
                tp_issue = _issue(
                    severity,
                    "transition_policy",
                    f"transition-policy {severity}: {tp_codes} — "
                    f"{(tp.get('issues') or [{}])[0].get('message', '')[:120]}",
                    fix=(
                        "continue 接戏缝→hard match-cut；场景硬切→禁 whip/grid；"
                        "段落转场→soft fade/dissolve；soft 风格轮转防粥。"
                        "旧片 soft：transition_policy_soft=true"
                    ),
                )
                if severity == "hard":
                    hard.append(tp_issue)
                else:
                    soft.append(tp_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "transition_policy_probe_error",
                    f"transition-policy probe failed: {exc}"[:200],
                    fix="check production_gates.transition_policy_report",
                )
            )

        # --- Controlled transition export read-back ---
        # Default HARD; legacy soft when transition_policy_soft=true.
        try:
            rb = transition_export_readback_report(spec)
            rb_codes = list(rb.get("codes") or [])
            if rb_codes:
                rb_hard = spec.get("transition_policy_soft") is not True
                rb_issue = _issue(
                    "hard" if rb_hard else "soft",
                    "transition_readback",
                    f"transition export read-back {'hard' if rb_hard else 'soft'}: "
                    f"{rb_codes} — {((rb.get('issues') or [{}])[0].get('message', '') or '')[:120]}",
                    fix=(
                        "build one operation per declared seam (continue→hard_cut/0.0s/no "
                        "overlay; soft→xfade with declared style; chapter→soft fade/dissolve; "
                        "scene cut→no whip/grid). 旧片 soft：transition_policy_soft=true"
                    ),
                )
                if rb_hard:
                    hard.append(rb_issue)
                else:
                    soft.append(rb_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "transition_readback_probe_error",
                    f"transition export read-back probe failed: {exc}"[:200],
                    fix="check production_gates.transition_export_readback_report",
                )
            )

        # --- Visual style-bible consistency (P2 · visual_bible 自动生成) ---
        # The style-bible is the canonical visual source of truth. When the spec
        # declares visual content, verify the on-disk style-bible.json is consistent
        # (hero cast master present; lighting timeline matches shot count). Missing /
        # inconsistent → recommend derive_style_bible_from_spec. Soft by default;
        # hard on style_bible_strict or adult max heat.
        try:
            sb = style_bible_consistency_report(spec, root=root)
            sb_codes = list(sb.get("codes") or [])
            if sb_codes:
                sb_strict = spec.get("style_bible_strict") is True or str(
                    spec.get("heat_scale") or ""
                ).lower() in {"max", "hot", "extreme"}
                sb_issue = _issue(
                    "hard" if sb_strict else "soft",
                    "style_bible_consistency",
                    f"style-bible consistency {'hard' if sb_strict else 'soft'}: {sb_codes} — "
                    f"{((sb.get('issues') or [{}])[0].get('message', '') or '')[:120]}",
                    fix=(
                        "run derive_style_bible_from_spec to auto-generate/refresh "
                        "style-bible.json (hero cast master + lighting timeline)."
                    ),
                )
                if sb_strict:
                    hard.append(sb_issue)
                else:
                    soft.append(sb_issue)
        except Exception as exc:
            _sb_heat = str(spec.get("heat_scale") or "").lower() in {"max", "hot", "extreme"}
            _sb_sev = "hard" if _sb_heat else "soft"
            _sb_iss = _issue(
                _sb_sev,
                "style_bible_consistency_probe_error",
                f"style-bible consistency probe failed: {exc}"[:200],
                fix="check production_gates.style_bible_consistency_report",
            )
            if _sb_sev == "hard":
                hard.append(_sb_iss)
            else:
                soft.append(_sb_iss)

        # Speaker ↔ picture (on_camera): soft by default; hard on max dialogue_drama (I2.3)
        try:
            from dialogue_speaker_frame_gate import (
                lint_dialogue_speaker_frame,
                lint_dialogue_still_recipe,
                speaker_frame_hard_enabled,
            )

            sf_hard = speaker_frame_hard_enabled(spec)
            sf_rep = lint_dialogue_speaker_frame(spec)
            bad_n = len(sf_rep.get("violations") or []) + len(sf_rep.get("window_violations") or [])
            if bad_n:
                codes = sorted(
                    {
                        str(v.get("code"))
                        for v in list(sf_rep.get("violations") or [])
                        + list(sf_rep.get("window_violations") or [])
                        if v.get("code")
                    }
                )
                sf_issue = _issue(
                    "hard" if sf_hard else "soft",
                    "speaker_frame",
                    f"speaker-frame {'hard' if sf_hard else 'soft'} lint: {codes} (n={bad_n})",
                    fix=(
                        "on_camera 台词镜 speaker 必须=画面主体(dsl.subject/cast)且与 "
                        "audio_cues.speaker 一致；同 beat 热窗内禁 speaker 翻转。"
                        "逃生: speaker_frame_strict:false"
                    ),
                )
                if sf_hard:
                    hard.append(sf_issue)
                else:
                    soft.append(sf_issue)
            # Wave 2 · dialogue still recipe (wide fullbody hanging lines)
            for sc in spec.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                for sh in sc.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    dr = lint_dialogue_still_recipe(sh)
                    for iss in dr.get("issues") or []:
                        sev = str(iss.get("severity") or "soft")
                        if sev == "hard" and not sf_hard:
                            sev = "soft"
                        item = _issue(
                            sev,
                            str(iss.get("code") or "dialogue_still_recipe"),
                            str(iss.get("msg") or iss.get("code")),
                            fix="on_camera 台词镜 still=speaker 脸 MCU/CU；禁全身肉戏 still 挂 A 台词",
                        )
                        if sev == "hard":
                            hard.append(item)
                        else:
                            soft.append(item)
        except Exception as exc:
            # A1 · when speaker-frame is hard mode, probe failure must hard-block
            try:
                from dialogue_speaker_frame_gate import speaker_frame_hard_enabled as _sfh

                _sf_hard_err = _sfh(spec)
            except Exception:
                _sf_hard_err = False
            _sev = "hard" if _sf_hard_err else "soft"
            _iss = _issue(
                _sev,
                "speaker_frame_probe_error",
                f"speaker-frame probe failed: {exc}"[:200],
                fix="check dialogue_speaker_frame_gate",
            )
            if _sev == "hard":
                hard.append(_iss)
            else:
                soft.append(_iss)

        # Wave 2 · dialogue_audio_lane required on spoken shots (native XOR post_tts)
        try:
            from dialogue_speaker_frame_gate import speaker_frame_hard_enabled
            from final.native_audio import lint_film_dialogue_audio_lanes

            lane_rep = lint_film_dialogue_audio_lanes(spec)
            if not lane_rep.get("ok"):
                miss = list(lane_rep.get("missing_lane_shots") or [])
                inv = list(lane_rep.get("invalid_lane_shots") or [])
                # invalid always hard; missing hard after write-spec once applied or explicit strict
                applied = isinstance(spec.get("_dialogue_audio_lanes"), dict)
                strict = spec.get("dialogue_audio_lane_strict") is True
                lane_hard = bool(inv) or (
                    bool(miss)
                    and (
                        strict
                        or applied
                        or speaker_frame_hard_enabled(spec)
                    )
                )
                msg = (
                    f"dialogue_audio_lane missing={miss[:8]} invalid={inv[:4]} "
                    f"(checked={lane_rep.get('checked')})"
                )
                lane_issue = _issue(
                    "hard" if lane_hard else "soft",
                    str(lane_rep.get("code") or "DIALOGUE_AUDIO_LANE_MISSING"),
                    msg,
                    fix=(
                        "每句对白镜写 dialogue_audio_lane=native|post_tts|silence；"
                        "aifilm write-spec 会默认 native。禁原声+Edge 双轨。"
                    ),
                )
                if lane_hard:
                    hard.append(lane_issue)
                else:
                    soft.append(lane_issue)
        except Exception as exc:
            try:
                from dialogue_speaker_frame_gate import speaker_frame_hard_enabled as _sfh2

                _lane_hard_err = _sfh2(spec)
            except Exception:
                _lane_hard_err = False
            _lane_sev = "hard" if _lane_hard_err else "soft"
            _lane_iss = _issue(
                _lane_sev,
                "dialogue_audio_lane_probe_error",
                f"dialogue_audio_lane probe failed: {exc}"[:200],
                fix="check final.native_audio.lint_film_dialogue_audio_lanes",
            )
            if _lane_sev == "hard":
                hard.append(_lane_iss)
            else:
                soft.append(_lane_iss)

        # Dramatic meaning stack (shot / motion / dialogue purpose / emotional_arc)
        try:
            from dramatic_meaning import lint_dramatic_meaning, meaning_gate_enabled

            shots_dm: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_dm.extend(sc["shots"])
            graph_path = root / "drama-graph.json"
            graph_dm = read_json(graph_path) if graph_path.is_file() else None
            if not isinstance(graph_dm, dict):
                graph_dm = None
            dm = lint_dramatic_meaning(spec, shots=shots_dm, graph=graph_dm)
            dm_codes = list(dm.get("codes") or [])
            if dm_codes:
                dm_strict = meaning_gate_enabled(spec)
                dm_msg = (
                    f"殿堂级意涵堆叠 {'hard' if dm_strict else 'soft'} lint: {dm_codes} "
                    f"(errors={dm.get('error_count')})"
                )
                dm_fix = (
                    "每镜 dramatic_function + visible_change/story_beat；"
                    "运镜回答 beat 故事问题（禁 blink/push-in 空转）；"
                    "对白须 speaker+text+subtext/emotion/purpose；"
                    "ordered shots 须穿过 director_intent.emotional_arc（禁单情绪趴平）。"
                    "见 lessons-2026-07-20-meaningful-motion.md · hard-defaults dramatic meaning"
                )
                dm_issue = _issue(
                    "hard" if dm_strict else "soft",
                    "dramatic_meaning",
                    dm_msg,
                    fix=dm_fix,
                )
                if dm_strict:
                    hard.append(dm_issue)
                else:
                    soft.append(dm_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "dramatic_meaning_probe_error",
                    f"dramatic meaning lint probe failed: {exc}"[:200],
                    fix="check dramatic_meaning.lint_dramatic_meaning",
                )
            )

        # --- Production consistency P2-2~P2-6 (wardrobe/hair/makeup/light/rhythm/lipsync/voice drift) ---
        # Soft by default; hard when production_consistency_strict (premium).
        try:
            from continuity import lint_production_consistency

            shots_pc: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_pc.extend(sc["shots"])
            if shots_pc:
                pcr = lint_production_consistency(shots_pc, bible=style, spec=spec)
                pc_codes = list(pcr.get("codes") or [])
                if pc_codes:
                    pc_strict = spec.get("production_consistency_strict") is True
                    pc_summary = (
                        f"production consistency drift: {pc_codes} "
                        f"(warn={pcr.get('warning_count')}) — "
                        f"{(pcr.get('issues') or [{}])[0].get('message', '')[:140]}"
                    )
                    pc_fix = (
                        "跨镜头一致性: 角色服装/发型/妆造/场景光影/运镜节奏/口型/声线 "
                        "须与 cast_locks/hair_swatches/make-up/wardrobe_variants 锚一致；"
                        "漂移只修上游（状态照/cast master），禁平行重抽。"
                        "见 references/consistency.md §1b/§1e · director-methodology.md §三-2"
                    )
                    pc_issue = _issue(
                        "hard" if pc_strict else "soft",
                        "production_consistency_drift",
                        pc_summary,
                        fix=pc_fix,
                    )
                    if pc_strict:
                        hard.append(pc_issue)
                    else:
                        soft.append(pc_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "production_consistency_probe_error",
                    f"production consistency lint probe failed: {exc}"[:200],
                    fix="check continuity.lint_production_consistency",
                )
            )

        # --- Composition rules P1-7 (180° axis / 30° / eyeline / size progression) ---
        # Soft by default; hard when composition_strict (premium).
        try:
            from framing_lint import lint_composition_rules

            shots_comp: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_comp.extend(sc["shots"])
            if len(shots_comp) >= 2:
                compr = lint_composition_rules(shots_comp)
                comp_codes = list(compr.get("codes") or [])
                if comp_codes:
                    comp_strict = spec.get("composition_strict") is True
                    comp_summary = (
                        f"composition rules violation: {comp_codes} "
                        f"(warn={compr.get('warning_count')}) — "
                        f"{(compr.get('issues') or [{}])[0].get('message', '')[:140]}"
                    )
                    comp_fix = (
                        "分镜构图法则: 180°轴线不跳（bridge/axis_break 例外）；"
                        "30°原则（相邻同景别须换角度）；eyeline match（视线方向→对侧）；"
                        "景别递进（禁连续3镜同 size）。见 references/director-methodology.md §二-10"
                    )
                    comp_issue = _issue(
                        "hard" if comp_strict else "soft",
                        "composition_rules_violation",
                        comp_summary,
                        fix=comp_fix,
                    )
                    if comp_strict:
                        hard.append(comp_issue)
                    else:
                        soft.append(comp_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "composition_rules_probe_error",
                    f"composition rules lint probe failed: {exc}"[:200],
                    fix="check framing_lint.lint_composition_rules",
                )
            )

        # --- Dialogue contract P1-8 (timing/origin/lipsync truth) ---
        # Soft by default; hard when dialogue_contract_strict (premium).
        try:
            from dialogue_contracts import summarize_dialogue_contracts

            shots_dc: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_dc.extend(sc["shots"])
            dc_summary = summarize_dialogue_contracts(shots_dc)
            dc_errors = dc_summary["errors"]
            if dc_errors:
                dc_strict = spec.get("dialogue_contract_strict") is True
                dc_codes = dc_summary["codes"]
                dc_message = (
                    f"dialogue contract violations: {dc_codes} "
                    f"({len(dc_errors)} errors) — "
                    f"{dc_errors[0].get('message', '')[:140]}"
                )
                dc_fix = (
                    "对白台词库: 每句对白须有 line_id + text_sha256 + delivery + 显式 lipsync_required；"
                    "对白窗口须在镜头窗口内；post_vo+silent I2V 非原生音频；"
                    "lipsync_required 须有 hash-bound 真实方法证据。"
                    "见 references/director-methodology.md §二-11 · dialogue_contract.py"
                )
                dc_issue = _issue(
                    "hard" if dc_strict else "soft",
                    "dialogue_contract_violation",
                    dc_message,
                    fix=dc_fix,
                )
                if dc_strict:
                    hard.append(dc_issue)
                else:
                    soft.append(dc_issue)
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "dialogue_contract_probe_error",
                    f"dialogue contract lint probe failed: {exc}"[:200],
                    fix="check dialogue_contract.validate_dialogue_contract",
                )
            )

        # --- Scene art / locations P3-13 (unregistered location, recurring objects, rules) ---
        # Soft by default.
        try:
            from asset_registry import lint_locations

            shots_loc: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_loc.extend(sc["shots"])
            # Load locations from assets-registry if it exists
            reg = read_json(root / "assets-registry.json") or {}
            locations = (
                reg.get("locations")
                if isinstance(reg.get("locations"), dict)
                else reg.get("locations")
            )
            if shots_loc and locations:
                loc_rep = lint_locations(shots_loc, locations)
                loc_codes = list(loc_rep.get("codes") or [])
                if loc_codes:
                    soft.append(
                        _issue(
                            "soft",
                            "scene_location_art",
                            f"scene art/location lint: {loc_codes} (warn={loc_rep.get('warning_count')})",
                            fix=(
                                "场景美术: 每镜 locationId 须在 assets-registry 注册；"
                                "recurring objects 须在 dsl 提及；immutableRules 不得违反。"
                                "见 references/director-methodology.md §二-8"
                            ),
                        )
                    )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="scene_location_probe_error",
                exc=exc,
                fix="check continuity.lint_locations / assets-registry",
            )

        # --- P4 fulfillment checks (act proportions, pace chart, music spotting) ---
        # Soft by default; hard when respective strict flag is set (premium).
        try:
            from rhythm import verify_act_structure, verify_music_spotting, verify_pace_chart

            shots_p4: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_p4.extend(sc["shots"])
            intent = spec.get("director_intent") if isinstance(spec, dict) else {}
            act_structure = intent.get("act_structure") if isinstance(intent, dict) else None
            pace_chart = intent.get("pace_chart") if isinstance(intent, dict) else None

            total_dur = (
                sum(float(s.get("duration_sec") or 0) for s in shots_p4 if isinstance(s, dict))
                or None
            )

            # P4-16: act structure fulfillment
            if act_structure and shots_p4:
                act_rep = verify_act_structure(shots_p4, act_structure, total_duration=total_dur)
                if not act_rep.get("ok"):
                    act_strict = spec.get("act_structure_strict") is True
                    p4_issue = _issue(
                        "hard" if act_strict else "soft",
                        "act_structure_fulfillment",
                        f"act ratio mismatch: {act_rep.get('codes')} — "
                        f"{(act_rep.get('issues') or [{}])[0].get('message', '')[:120]}",
                        fix="调整镜头 dramatic_function 分布或 duration_sec 使实际幕比例匹配 act_structure 声明",
                    )
                    if act_strict:
                        hard.append(p4_issue)
                    else:
                        soft.append(p4_issue)

            # P4-17: pace chart fulfillment
            if pace_chart and shots_p4:
                pace_rep = verify_pace_chart(shots_p4, pace_chart, total_duration=total_dur)
                if not pace_rep.get("ok"):
                    pace_strict = spec.get("pace_chart_strict") is True
                    p4_issue = _issue(
                        "hard" if pace_strict else "soft",
                        "pace_chart_fulfillment",
                        f"pace chart mismatch: {pace_rep.get('codes')} — "
                        f"{(pace_rep.get('issues') or [{}])[0].get('message', '')[:120]}",
                        fix="调整镜头密度/duration 使实际切镜频率匹配 pace_chart 声明曲线",
                    )
                    if pace_strict:
                        hard.append(p4_issue)
                    else:
                        soft.append(p4_issue)

            # P4-18: music spotting beat alignment
            sound_plan = spec.get("sound_plan") if isinstance(spec, dict) else {}
            music_spotting = (
                sound_plan.get("music_spotting") if isinstance(sound_plan, dict) else None
            )
            if music_spotting and isinstance(music_spotting, list):
                beats = intent.get("beats") if isinstance(intent, dict) else None
                music_rep = verify_music_spotting(music_spotting, beats, total_duration=total_dur)
                if not music_rep.get("ok"):
                    p4_issue = _issue(
                        "soft",
                        "music_spotting_alignment",
                        f"music spotting alignment: {music_rep.get('codes')} — "
                        f"{(music_rep.get('issues') or [{}])[0].get('message', '')[:120]}",
                        fix="修正 music_spotting beat_ref / start_sec / end_sec 与 beats 时间轴对齐",
                    )
                    soft.append(p4_issue)
        except Exception as exc:
            p4_hard = (
                spec.get("act_structure_strict") is True or spec.get("pace_chart_strict") is True
            )
            _append_probe_error(
                hard,
                soft,
                code="p4_fulfillment_probe_error",
                exc=exc,
                fix="check rhythm.verify_act_structure / pace_chart / music_spotting",
                hard_mode=p4_hard,
            )
        try:
            from continuity_chain import check_continuity_chain, is_long_form

            shots_lf: list = []
            if isinstance(spec.get("scenes"), list):
                for sc in spec["scenes"]:
                    if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
                        shots_lf.extend(sc["shots"])
            if is_long_form(spec, shots_lf):
                ccr = check_continuity_chain(root, spec, strict=False, require_doc_if_long=True)
                if not ccr.get("doc_present"):
                    hard.append(
                        _issue(
                            "hard",
                            "continuity_chain_doc",
                            "长片缺少 continuity_chain.md（动作串接清单）",
                            fix='aifilm continuity-chain init --root "' + str(root) + '"',
                        )
                    )
                for iss in ccr.get("hard") or []:
                    hard.append(
                        _issue(
                            "hard",
                            str(iss.get("code") or "continuity_chain"),
                            str(iss.get("message") or "continuity chain hard fail"),
                            fix=(
                                "continue 缝: extract-frame --promote-keyframe；"
                                "九项核对全 pass；禁止后期掩盖。见 references/continuity_chain.md"
                            ),
                        )
                    )
                for iss in ccr.get("soft") or []:
                    soft.append(
                        _issue(
                            "soft",
                            str(iss.get("code") or "continuity_chain"),
                            str(iss.get("message") or "continuity chain soft"),
                            fix="补 continuity_chain.md 九项核对 / receipts/frame-chain.json",
                        )
                    )
                # Programmatic MVP (v2.40): forbidden joins + frame hash when files exist
                try:
                    from continuity_programmatic import check_continuity_programmatic

                    cpr = check_continuity_programmatic(root, write=True)
                    for iss in cpr.get("issues") or []:
                        code = str(iss.get("code") or "continuity_prog")
                        sev = (
                            "hard"
                            if code
                            in {
                                "CHAIN_DOC_MISSING",
                                "CONTINUE_FORBIDDEN_TRANSITION",
                                "CONTINUE_FRAME_HASH_MISMATCH",
                            }
                            else "soft"
                        )
                        bucket = hard if sev == "hard" else soft
                        bucket.append(
                            _issue(
                                sev,
                                code,
                                str(iss.get("message") or "continuity programmatic"),
                                fix="continue 缝 byte match + 禁 dissolve 盖缝；见 continuity_programmatic",
                            )
                        )
                except Exception as exc:
                    _append_probe_error(
                        hard,
                        soft,
                        code="continuity_programmatic_probe_error",
                        exc=exc,
                        fix="check continuity_programmatic.check_continuity_programmatic",
                    )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="continuity_chain_probe_error",
                exc=exc,
                fix="check continuity_chain.check_continuity_chain",
            )

        # TTS language ping-pong hard (v2.40): no ja cast_voices / ja dialogue_spoken_lang
        try:
            cast_voices = spec.get("cast_voices") if isinstance(spec.get("cast_voices"), dict) else {}
            for role, vid in cast_voices.items():
                if isinstance(vid, str) and (
                    vid.lower().startswith("ja-") or "ja-jp" in vid.lower()
                ):
                    hard.append(
                        _issue(
                            "hard",
                            "voice_lang_ja_cast",
                            f"cast_voices[{role}]={vid!r} is Japanese; Chinese-only (v2.40)",
                            fix="normalize cast_voices to zh-CN-* Edge ids",
                        )
                    )
            dlang = str(spec.get("dialogue_spoken_lang") or "zh").strip().lower()
            if dlang in {"ja", "jp", "japanese"}:
                hard.append(
                    _issue(
                        "hard",
                        "voice_lang_ja_dialogue",
                        "dialogue_spoken_lang=ja is retired; use zh",
                        fix="set dialogue_spoken_lang=zh",
                    )
                )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="voice_lang_probe_error",
                exc=exc,
                fix="check cast_voices / dialogue_spoken_lang",
            )

        # signature accessories in identity_lock if style has cast
        id_lock = style.get("identity_lock") if isinstance(style, dict) else None
        if isinstance(id_lock, str) and "halo" not in id_lock.lower() and "光环" not in id_lock:
            # only soft if theme looks like kei-like; keep generic soft for empty lock
            if not id_lock.strip():
                soft.append(
                    _issue(
                        "soft",
                        "identity_lock_empty",
                        "identity_lock 为空 — 签名配件易丢",
                        fix="style-bible identity_lock 写死配件（如粉光环）",
                    )
                )

    # --- pilot (S3 + 2026-07-17) ---
    pilot_ok = pilot_is_user_approved(pilot)
    score_ok = (
        isinstance(score, dict)
        and score.get("kind") == "pilot-scorecard"
        and score.get("all_pass") is True
    )
    if not pilot_ok:
        soft.append(
            _issue(
                "soft",
                "pilot_not_user_approved",
                "无用户 pilot 批准 — bulk 最多 3 个不同 shot_id",
                fix='aifilm pilot report → score → approve --user-phrase "pilot 过"',
            )
        )
    if pilot_ok and not score_ok:
        soft.append(
            _issue(
                "soft",
                "pilot_without_scorecard",
                "已有 user pilot 但无三维 scorecard 全 pass 记录",
                fix="建议补 aifilm pilot score 留下验收痕迹",
            )
        )
    if score_ok and not pilot_ok:
        soft.append(
            _issue(
                "soft",
                "scorecard_awaiting_phrase",
                "pilot score 已过，等用户原话 approve",
                fix='aifilm pilot approve --user-phrase "pilot 过"',
            )
        )
    if isinstance(score, dict) and score.get("failures"):
        soft.append(
            _issue(
                "soft",
                "pilot_score_failures",
                f"pilot scorecard failures={score.get('failures')}",
                fix="修 still/I2V 后重 score；已写入 director_notes（若未 --no-notes-on-fail）",
            )
        )

    # --- clips / final ---
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    approved_clip_ids = [
        sid
        for sid, rec in clips.items()
        if isinstance(rec, dict) and rec.get("status") == "approved"
    ]
    approved_clips = len(approved_clip_ids)
    gates = man.get("gates") if isinstance(man.get("gates"), dict) else {}
    if gates.get("clips_complete") is False and approved_clips == 0:
        soft.append(
            _issue(
                "soft",
                "no_clips",
                "尚无 approved clips",
                fix="pilot 三镜 I2V → register-clip",
            )
        )

    # Shot inventory consistency (sediment cn/codex): fail closed on partial sets
    shot_ids_for_inv: list[str] = []
    if spec:
        try:
            from film_spec import validate_film_spec

            shot_ids_for_inv = [
                str(s["id"]) for s in validate_film_spec(spec, assign_missing_ids=False)
            ]
            shot_ids_for_inv.extend(
                str(entry.get("id"))
                for shot in validate_film_spec(spec, assign_missing_ids=False)
                for entry in (shot.get("dialogue_broll") or [])
                if isinstance(entry, dict) and str(entry.get("id") or "").strip()
            )
        except Exception:
            # fall back to raw ids without full validation
            for scene in spec.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict) and sh.get("id"):
                        shot_ids_for_inv.append(str(sh["id"]))
    inventory_report: dict[str, Any] | None = None
    if shot_ids_for_inv:
        try:
            from shot_inventory import check_shot_inventory, discover_vo_stem_ids

            vo_ids = discover_vo_stem_ids(root)
            require_vo = bool(vo_ids)  # if stems exist, they must match shots
            inventory_report = check_shot_inventory(
                shot_ids_for_inv,
                approved_clip_ids,
                vo_stem_ids=vo_ids if vo_ids else None,
                require_vo=require_vo,
            )
            # Partial production (some but not all clips) is hard — never index past missing
            if inventory_report.get("partial"):
                hard.append(
                    _issue(
                        "hard",
                        "inventory_mismatch",
                        (
                            f"shot inventory partial: missing={inventory_report.get('missing_clips')} "
                            f"extra={inventory_report.get('extra_clips')} "
                            f"({inventory_report.get('approved_clip_count')}/"
                            f"{inventory_report.get('shot_count')} clips)"
                        ),
                        fix="register missing clips or remove orphan approved entries; do not final on partial set",
                    )
                )
            if require_vo and "VO_INVENTORY_MISMATCH" in (inventory_report.get("codes") or []):
                hard.append(
                    _issue(
                        "hard",
                        "vo_inventory_mismatch",
                        (
                            f"VO stems ≠ shots: missing={inventory_report.get('missing_vo')} "
                            f"extra={inventory_report.get('extra_vo')}"
                        ),
                        fix="re-run final TTS or tts-rehearse so each shot has a stem",
                    )
                )
            # Manifest claims clips_complete but inventory says otherwise
            if gates.get("clips_complete") is True and not inventory_report.get("complete"):
                hard.append(
                    _issue(
                        "hard",
                        "inventory_gate_lie",
                        "manifest.gates.clips_complete=true but shot set ≠ approved clips",
                        fix="aifilm status 重算 gates；补齐 register-clip",
                    )
                )
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "inventory_probe_error",
                    f"inventory check failed: {exc}"[:200],
                    fix="check shot_inventory.py / film-spec",
                )
            )

    # True-video-only: approved clips must be generative video (not Ken Burns / still-motion)
    true_video_report: dict[str, Any] | None = None
    if approved_clips > 0:
        try:
            from true_video_policy import scan_manifest_true_video

            true_video_report = scan_manifest_true_video(root, manifest=man)
            if not true_video_report.get("ok") and not true_video_report.get("skipped"):
                viol = true_video_report.get("violations") or []
                hard.append(
                    _issue(
                        "hard",
                        "true_video_policy",
                        (
                            f"hero track has {len(viol)} still-motion/non-video approved clip(s): "
                            + ", ".join(str(v.get("shot_id")) for v in viol[:6])
                        ),
                        fix=(
                            "re-I2V with Grok/H3; ban Ken Burns/panel zoompan on hero; "
                            "stills are inputs only"
                        ),
                    )
                )
        except Exception as exc:
            soft.append(
                _issue(
                    "soft",
                    "true_video_probe_error",
                    f"true_video scan failed: {exc}"[:200],
                    fix="check true_video_policy.py",
                )
            )

    # Evidence separation soft risks (intent ≠ executed ≠ human)
    evidence: dict[str, Any] | None = None
    try:
        from evidence_status import classify_evidence

        evidence = classify_evidence(root)
        for risk in evidence.get("impersonation_risks") or []:
            if not isinstance(risk, dict):
                continue
            soft.append(
                _issue(
                    "soft",
                    str(risk.get("code") or "evidence_risk"),
                    str(risk.get("message") or "evidence separation risk"),
                    fix="status.evidence 区分 intent/executed/human_review；勿把 plan 当交付",
                )
            )
    except Exception:
        evidence = None

    # designed-post tooling (soft)
    try:
        from compose_render import probe_designed_post_tooling, probe_remotion_readiness

        tooling = probe_designed_post_tooling()
        if not tooling.get("hyperframes_ok"):
            soft.append(
                _issue(
                    "soft",
                    "hyperframes_unavailable",
                    f"HyperFrames 不可用: {tooling.get('error') or 'npx/hyperframes'}",
                    fix="装 Node 22+ 或只用 --post-engine ffmpeg",
                )
            )
        # Remotion: only soft-warn when package exported but not bootstrapped
        rem_pkg = root / "compose" / "remotion" / "package.json"
        if rem_pkg.is_file():
            rem = probe_remotion_readiness(root)
            if not rem.get("ready"):
                missing = ", ".join(rem.get("missing") or ["node_modules"])
                soft.append(
                    _issue(
                        "soft",
                        "remotion_not_ready",
                        f"compose/remotion 已导出但未就绪: {missing}",
                        fix=(
                            f'cd "{root}/compose/remotion" && npm install；'
                            "或 aifilm compose-render --engine remotion 看 next_steps；"
                            "主路径用 --post-engine hyperframes"
                        ),
                    )
                )
        # Preview receipt soft nudge when clips complete and no final yet
        try:
            from compose_preview import has_valid_preview_receipt

            outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
            has_final = isinstance(outputs.get("final_film"), dict)
            if (
                gates.get("clips_complete")
                and not has_final
                and not has_valid_preview_receipt(root)
            ):
                soft.append(
                    _issue(
                        "soft",
                        "compose_preview_recommended",
                        "clips 已齐、尚未 final — 建议先 compose-preview 再设计成片",
                        fix=f'aifilm compose-preview --root "{root}"',
                    )
                )
            if (
                gates.get("clips_complete")
                and not has_final
                and not (root / "post-plan.json").is_file()
            ):
                soft.append(
                    _issue(
                        "soft",
                        "post_plan_missing",
                        "设计后期尚未锁定唯一 owner；先选 HyperFrames 或 Remotion，避免双烧字幕/双 final",
                        fix=f'aifilm post-plan --root "{root}" init --owner hyperframes',
                    )
                )
        except Exception as exc:
            _append_probe_error(
                hard,
                soft,
                code="compose_preview_probe_error",
                exc=exc,
                fix="check compose_preview.has_valid_preview_receipt",
            )
    except Exception as exc:
        soft.append(
            _issue(
                "soft", "hyperframes_probe_error", str(exc)[:200], fix="检查 compose_render 导入"
            )
        )

    # concurrent final warning file
    work = root / "out" / "_final_work"
    if work.is_dir():
        soft.append(
            _issue(
                "soft",
                "final_work_present",
                "out/_final_work 仍在 — 可能有未完成/崩溃的 final",
                fix="确认无 final 进程后 rm -rf out/_final_work 再 final",
            )
        )

    # --- keyframe geometry / no-compress (lesson 2026-07-22 · vivian-ep01) ---
    keyframe_geo_report: dict[str, Any] | None = None
    try:
        from media_qa import analyze_still_geometry, pick_best_keyframe

        aspect = (
            str((spec or {}).get("aspect_ratio") or "9:16") if isinstance(spec, dict) else "9:16"
        )
        shot_list: list[Any] = []
        if isinstance(spec, dict):
            for sc in spec.get("scenes") or []:
                if isinstance(sc, dict):
                    shot_list.extend(sc.get("shots") or [])
        bad_geo: list[dict[str, Any]] = []
        soft_geo: list[str] = []
        for sh in shot_list:
            if not isinstance(sh, dict):
                continue
            sid = str(sh.get("id") or "")
            if not sid:
                continue
            kf = pick_best_keyframe(root, sid)
            if kf is None:
                continue  # missing handled elsewhere
            geo = analyze_still_geometry(kf, aspect_ratio=aspect)
            if not geo.get("ok"):
                bad_geo.append(
                    {
                        "shot_id": sid,
                        "path": str(kf),
                        "width": geo.get("width"),
                        "height": geo.get("height"),
                        "codes": geo.get("codes"),
                        "errors": geo.get("errors"),
                    }
                )
            for scode in geo.get("soft_codes") or []:
                soft_geo.append(f"{sid}:{scode}")
        keyframe_geo_report = {
            "ok": len(bad_geo) == 0,
            "bad": bad_geo,
            "soft": soft_geo,
            "checked": len(shot_list),
        }
        if bad_geo:
            sample = bad_geo[:5]
            hard.append(
                _issue(
                    "hard",
                    "KEYFRAME_COMPRESS_OR_ASPECT",
                    "keyframe 分辨率/画幅不合格（压缩或横图会传染整段 I2V）: "
                    + "; ".join(
                        f"{b['shot_id']}={b.get('width')}x{b.get('height')} {b.get('codes')}"
                        for b in sample
                    )
                    + (f" …(+{len(bad_geo) - 5})" if len(bad_geo) > 5 else ""),
                    fix=(
                        "re-export still ≥720×1280 9:16 full-res; use pick_best_keyframe (prefer png); "
                        "never I2V from thumbnail. lessons-2026-07-22-keyframe-no-compress.md"
                    ),
                )
            )
        if soft_geo:
            soft.append(
                _issue(
                    "soft",
                    "KEYFRAME_BYTES_LOW",
                    f"keyframe file very small (possible heavy JPEG): {soft_geo[:8]}",
                    fix="prefer png / high-quality jpg; eye-check for blocky mush",
                )
            )
    except Exception as exc:
        soft.append(
            _issue(
                "soft",
                "keyframe_geometry_probe_error",
                f"keyframe geometry probe failed: {exc}"[:200],
                fix="check media_qa.analyze_still_geometry",
            )
        )

    # --- state-index checkpoint (keyframe-first + fluent joins) ---
    state_index_report: dict[str, Any] | None = None
    try:
        from state_index_gate import run_state_index_check, write_state_index_receipt

        state_index_report = run_state_index_check(root)
        write_state_index_receipt(root, state_index_report)
        for iss in state_index_report.get("hard") or []:
            if not isinstance(iss, dict):
                continue
            hard.append(
                _issue(
                    "hard",
                    str(iss.get("code") or "state_index"),
                    str(iss.get("message") or "state-index hard"),
                    fix=str(iss.get("fix") or "aifilm state-index plan --root …"),
                )
            )
        for iss in state_index_report.get("soft") or []:
            if not isinstance(iss, dict):
                continue
            soft.append(
                _issue(
                    "soft",
                    str(iss.get("code") or "state_index"),
                    str(iss.get("message") or "state-index soft"),
                    fix=str(iss.get("fix") or "aifilm state-index plan --root …"),
                )
            )
        # If generate_plan non-empty and production mid-flight, surface as soft checkpoint
        plan = state_index_report.get("generate_plan") or []
        if plan and not state_index_report.get("ok"):
            soft.append(
                _issue(
                    "soft",
                    "state_index_regen_needed",
                    f"state-index: {len(plan)} regenerate item(s) for fluid transitions",
                    fix=f'aifilm state-index plan --root "{root}"',
                )
            )
    except Exception as exc:
        soft.append(
            _issue(
                "soft",
                "state_index_probe_error",
                f"state-index gate failed: {exc}"[:200],
                fix="check state_index_gate.py",
            )
        )

    try:
        from timeline_clock import audit_timeline_clock
        clock = audit_timeline_clock(root, write=True)
        if clock.get("dual_clock"):
            hard.append(_issue("hard", "DUAL_TIMELINE_CLOCK", str(clock.get("error") or "dual clock"), fix=str(clock.get("next_cmd") or "")))
    except Exception as exc:
        soft.append(_issue("soft", "timeline_clock_probe_error", str(exc)[:200]))
    try:
        from post_doctor import run_post_doctor
        doctor = run_post_doctor(root, write=True)
        for iss in doctor.get("hard") or []:
            if not isinstance(iss, dict):
                continue
            code = str(iss.get("code") or "")
            sev = "hard" if code in {"DOUBLE_BURN_RISK", "SRT_OVERLAP", "SRT_BAD_CUE", "DUAL_TIMELINE_CLOCK", "CAPTION_PIXEL_RED"} else "soft"
            (hard if sev=="hard" else soft).append(_issue(sev, code, str(iss.get("message") or code), fix=str(iss.get("fix") or "")))
        for iss in doctor.get("soft") or []:
            if isinstance(iss, dict):
                soft.append(_issue("soft", str(iss.get("code") or "post_doctor"), str(iss.get("message") or "")))
    except Exception as exc:
        soft.append(_issue("soft", "post_doctor_probe_error", str(exc)[:200]))

    hard_ok = len(hard) == 0
    try:
        from next_actions import build_next_actions, detect_pipeline_stage

        next_actions = build_next_actions(root, gates=gates)
        pipeline_stage = detect_pipeline_stage(root, gates=gates)
    except Exception:
        next_actions = []
        pipeline_stage = {"stage": "unknown", "label_zh": "未知"}

    # Prefer state-index fix when plan non-empty and still in visual/agent
    if state_index_report and (state_index_report.get("generate_plan") or []):
        si_cmd = f'aifilm state-index plan --root "{root}"'
        if not next_actions or not str((next_actions[0] or {}).get("cmd") or "").startswith(
            "aifilm state-index"
        ):
            next_actions = [
                {
                    "id": "state-index-plan",
                    "cmd": si_cmd,
                    "why": "状态照/keyframe/promote 检查有缺口 — 先补再 bulk，保障运镜转场流畅",
                    "stage": "visual",
                    "stage_label": "1·视觉",
                    "source": "state_index_gate",
                }
            ] + list(next_actions or [])

    return {
        "ok": hard_ok,
        "hard_ok": hard_ok,
        "soft_ok": len(soft) == 0,
        "root": str(root),
        "checked_at": utc_now(),
        "hard": hard,
        "soft": soft,
        "counts": {"hard": len(hard), "soft": len(soft), "approved_clips": approved_clips},
        "inventory": inventory_report,
        "evidence": evidence,
        "tts_timing": tts_timing,
        "state_index": state_index_report,
        "pilot": {
            "user_approved": pilot_ok,
            "scorecard_all_pass": score_ok,
        },
        "pipeline_stage": pipeline_stage,
        "stage": pipeline_stage.get("stage") if isinstance(pipeline_stage, dict) else None,
        "stage_label": pipeline_stage.get("label_zh") if isinstance(pipeline_stage, dict) else None,
        "next_actions": next_actions,
        "next_cmd": next_actions[0]["cmd"] if next_actions else None,
        "keyframe_geometry": keyframe_geo_report,
        "lessons": [
            "references/pipeline-methodology.md",
            "references/keyframe-first-state-index.md",
            "references/lessons-2026-07-16-kei.md",
            "references/lessons-2026-07-17-compose-pilot.md",
            "references/lessons-2026-07-20-sediment-cn-codex.md",
            "references/lessons-2026-07-21-sex-duration-floor.md",
            "references/lessons-2026-07-21-sex-undress-ladder.md",
            "references/lessons-2026-07-21-sex-vo-spice.md",
            "references/lessons-2026-07-21-wardrobe-no-redress-still.md",
            "references/lessons-2026-07-22-keyframe-no-compress.md",
            "references/lessons-2026-07-22-verify-before-generate.md",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Lesson-based production preflight")
    p.add_argument("--root", required=True)
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on any soft warning too",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_preflight(Path(args.root))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["hard_ok"]:
            return 2
        if args.strict and not report["soft_ok"]:
            return 3
        return 0
    except PreflightError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
