"""BGM + shot loop + edit craft body of film_spec validation (W2 residual peel).

Structure-only. Called after provider leaf; returns shots for soft/heat leaves.
"""

from __future__ import annotations

from typing import Any

from audio_recipe import (
    AudioRecipeError,
    apply_audio_recipes_to_spec,
    probe_caps_for_root,
)
from dialogue_broll import DialogueBrollError, iter_dialogue_broll, validate_dialogue_broll
from edit_policy import (
    _CRAFT_WHY,
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    apply_coverage_defaults_to_shot,
    edit_crafts_to_intents,
    enforce_continue_hard_joins,
    normalize_edit_craft,
    normalize_transition_intent,
    normalize_transition_sec,
    normalize_transition_styles,
    suggest_edit_crafts,
    suggest_transition_intents,
    suggest_transition_styles,
    validate_motion,
)
from security_policy import SecurityPolicyError, validate_identifier
from sound_plan import (
    SoundPlanError,
    default_sound_plan_for_film,
    inject_auto_sfx_if_empty,
    inject_music_energy_spotting,
    inject_sex_sfx_from_shots,
    resolve_sidechain,
    validate_sound_plan,
)
from transition_ops import TransitionOperationError, build_transition_operations

try:
    from plan.film_spec_constants import *  # noqa: F403
except ImportError:  # pragma: no cover
    from film_spec_constants import *  # type: ignore  # noqa: F403
from film_spec_profile import (  # noqa: F401
    DEFAULT_H3_CONFIG,
    FRW_I2V_FRW_ONLY_LIFEBOAT,
    I2V_PROVIDERS,
    default_frw_video_model,
    default_i2v_provider,
    frw_i2v_fallback_chain,
    resolve_h3_config,
    resolve_i2v_profile,
)
from plan.film_spec_lints import (  # noqa: F401
    _PERFORMANCE_PLACEHOLDERS,
    DIRECTOR_BOARD_FIELDS,
    PERFORMANCE_FIELDS,
    FilmSpecError,
    _is_unauthored,
    _required_text,
    _validate_dialogue_drama_shot,
    estimate_nar_vo_sec,
    iter_film_spec_shots,
    lint_director_board,
    lint_performance,
    validate_director_intent,
    validate_dramatic_function,
    validate_nar_budget,
    zero_narration_gate,
)


def apply_bgm_shots_and_edit_body(
    spec: dict[str, Any],
    *,
    mode: str,
    assign_missing_ids: bool,
    film_root: Any | None = None,
) -> list[dict[str, Any]]:
    """Mutate spec; return validated shots list for soft/heat leaves."""
    # BGM: 色气/storyteller default rnb (R&B/Soul seductive). dark only for horror.
    intent_for_sound = (
        spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    )
    tone_txt = str((intent_for_sound or {}).get("tone") or "")
    try:
        if spec.get("sound_plan") is None:
            # Auto-inject so agents don't forget and fall into dark by accident
            sound = default_sound_plan_for_film(
                vo_mode=str(spec.get("vo_mode") or "storyteller"),
                tone=tone_txt,
                title=str(spec.get("title") or ""),
                description=str(spec.get("description") or ""),
            )
            sound["_notes"] = ["auto-injected default sound_plan (mood=rnb for 色气/storyteller)"]
        else:
            sound = validate_sound_plan(
                spec.get("sound_plan"),
                tone=tone_txt,
                title=str(spec.get("title") or ""),
                description=str(spec.get("description") or ""),
                vo_mode=str(spec.get("vo_mode") or ""),
            )
    except SoundPlanError as exc:
        raise FilmSpecError(str(exc)) from exc
    if sound is not None:
        # rnb family: pin sidechain so VO pauses breathe (Phase F; author can override)
        mood_l = str(sound.get("mood") or "").lower()
        if mood_l in {"rnb", "sensual", "soul", "seductive", "ecchi"} and not sound.get(
            "sidechain"
        ):
            sc = resolve_sidechain(sound, mood=mood_l)
            sound["sidechain"] = {
                "threshold": sc["threshold"],
                "ratio": sc["ratio"],
                "attack_ms": sc["attack_ms"],
                "release_ms": sc["release_ms"],
            }
            sn = list(sound.get("_notes") or [])
            sn.append(
                f"auto-injected rnb sidechain release_ms={sc['release_ms']:.0f} (VO pause breath)"
            )
            sound["_notes"] = sn
        spec["sound_plan"] = sound
        if sound.get("_notes"):
            spec.setdefault("_sound_plan_notes", list(sound.get("_notes") or []))

    scenes = spec.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise FilmSpecError("film-spec requires non-empty scenes")

    shots: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_axes: list[str] = []
    previous_viewpoints: list[str] = []
    previous_focal: str | None = None
    previous_viewpoint: str | None = None
    _vo_lint_violations: list[dict[str, Any]] = []  # P2-10: collected for vo_lint_strict
    previous_look: str | None = None
    previous_end_pose: str | None = None
    # Cast ids for multi-stance (style-bible keys or director_intent.cast)
    cast_ids: list[str] = []
    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    raw_cast = di.get("cast") or di.get("characters") or spec.get("cast_ids")
    if isinstance(raw_cast, list):
        cast_ids = [str(x).strip() for x in raw_cast if str(x).strip()]
    elif isinstance(raw_cast, dict):
        cast_ids = [str(k).strip() for k in raw_cast if str(k).strip()]
    # style-bible may not be in film-spec; optional cast_masters on spec
    cm = spec.get("cast_masters")
    if isinstance(cm, dict):
        for k in cm:
            if str(k).strip() and str(k) not in cast_ids:
                cast_ids.append(str(k).strip())
    if not cast_ids:
        cast_ids = ["hero", "partner"]

    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise FilmSpecError(f"scene {scene_index} must be an object")
        scene_shots = scene.get("shots")
        if scene_shots is None:
            scene_shots = []
        if not isinstance(scene_shots, list):
            raise FilmSpecError(f"scene {scene_index} shots must be an array")
        for shot in scene_shots:
            if not isinstance(shot, dict):
                raise FilmSpecError(f"scene {scene_index} contains a non-object shot")
            if not shot.get("id") and assign_missing_ids:
                shot["id"] = f"shot{len(shots) + 1:02d}"
            try:
                shot_id = validate_identifier(shot.get("id"), field="shot id")
            except SecurityPolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            if shot_id in seen:
                raise FilmSpecError(f"duplicate shot id: {shot_id}")
            seen.add(shot_id)
            if shot.get("dialogue_broll") is not None:
                try:
                    validate_dialogue_broll(shot, shot_id=shot_id)
                except DialogueBrollError as exc:
                    raise FilmSpecError(str(exc)) from exc
            if mode == "dialogue_drama":
                _validate_dialogue_drama_shot(
                    shot,
                    shot_id=shot_id,
                    narration_gap_strict=spec.get("narration_gap_strict") is True,
                )
                nar = shot.get("nar")
                if nar is not None:
                    shot["nar"] = validate_nar_budget(nar, field=f"{shot_id}.nar")
                else:
                    shot["est_vo_sec"] = 0.0
            else:
                shot["nar"] = validate_nar_budget(shot.get("nar"), field=f"{shot_id}.nar")
            # v1.23: VO script lint — brochure phrase / AI-cadence / long-sentence warnings.
            # Advisory only (warnings); genre=product can elevate to hard gate.
            from vo_lint import lint_nar_text

            _vo_warnings = lint_nar_text(str(shot.get("nar") or ""), shot_id=shot_id)
            if _vo_warnings:
                shot.setdefault("_vo_lint_warnings", [w.to_dict() for w in _vo_warnings])
                for w in _vo_warnings:
                    _vo_lint_violations.append({"shot_id": shot_id, **w.to_dict()})
            elif "_vo_lint_warnings" in shot:
                del shot["_vo_lint_warnings"]
            # Optional English line for dual captions (designed-post); not TTS-spoken by default
            nar_en = shot.get("nar_en")
            if nar_en is not None:
                if not isinstance(nar_en, str):
                    raise FilmSpecError(f"{shot_id}.nar_en must be a string")
                shot["nar_en"] = nar_en.strip()
            shot["est_vo_sec"] = estimate_nar_vo_sec(str(shot.get("nar") or ""))
            shot["dramatic_function"] = validate_dramatic_function(
                shot.get("dramatic_function"),
                field=f"{shot_id}.dramatic_function",
            )
            # Layer role: hero (identity I2V) vs env/bridge/insert (LTX T2V synth beds)
            raw_role = shot.get("shot_role")
            if raw_role is None or (isinstance(raw_role, str) and not raw_role.strip()):
                dsl0 = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
                cast0 = dsl0.get("cast") if isinstance(dsl0, dict) else None
                has_cast = bool(cast0)
                # subject alone is weak signal — default hero for safety (identity first)
                fn0 = shot["dramatic_function"]
                if fn0 == "bridge" and not has_cast:
                    role = "env"
                elif fn0 == "bridge":
                    role = "bridge"
                else:
                    role = DEFAULT_SHOT_ROLE
            else:
                if not isinstance(raw_role, str) or raw_role.lower() not in SHOT_ROLES:
                    raise FilmSpecError(f"{shot_id}.shot_role must be one of {sorted(SHOT_ROLES)}")
                role = raw_role.lower()
            shot["shot_role"] = role
            # Recommend engine per layer (agent CLI; not auto-dispatched)
            if role == "hero":
                shot["_recommended_engine"] = {
                    "still": "grok_image_edit_cast",
                    "motion": "frw_video_model_i2v_or_grok",
                    "frw_model_field": "frw_video_model",
                    "forbid": ["ltx-t2v_as_face", "legacy-img2video_default"],
                }
            else:
                shot["_recommended_engine"] = {
                    "still": "optional_empty_or_style_only",
                    "motion": "frw_env_model_t2v",
                    "frw_model_field": "frw_env_model",
                    "primary": DEFAULT_FRW_ENV_MODEL,
                    "forbid": ["claim_identity_lock_from_t2v"],
                }
            if mode == "dialogue_drama" and shot.get("screen_mode") == "on_camera":
                shot.setdefault("dialogue_motion_route", "auto")
                shot["_recommended_engine"] = {
                    "state_still": "comfy_qwen_i2i_performance_state",
                    "keyframe": "comfy_qwen_i2i_from_performance_state",
                    "motion": "frw_ltx23_img2video_audio",
                    "motion_primary": "frw_ltx23_img2video_audio",
                    "motion_fallback": "frw_img2video_rejection_only",
                    "lipsync_primary": "frw_ltx23_native_audio_i2v_human_verified",
                    "lipsync_fallback": "rtx_latentsync_1_6_after_frw_img2video_fallback",
                    "fallback_trigger": "reviewed_ltx_native_audio_rejection_only",
                    "native_text_gate": "reject_provider_burned_text_before_post",
                    "forbid": [
                        "quality_rejection_as_provider_fallback",
                        "unreviewed_lipsync",
                        "provider_burned_text",
                        "full_cast_reference_when_state_photo_exists",
                        "experimental_whole_frame_talking_as_default",
                    ],
                }
            # B1: motion/size/axis + character stance (focal/viewpoint/look_axis)
            try:
                cov = apply_coverage_defaults_to_shot(
                    shot,
                    dramatic_function=shot["dramatic_function"],
                    shot_index=len(shots),
                    previous_axes=previous_axes,
                    previous_focal=previous_focal,
                    previous_viewpoints=previous_viewpoints,
                    previous_viewpoint=previous_viewpoint,
                    previous_look=previous_look,
                    previous_end_pose=previous_end_pose,
                    cast_ids=cast_ids,
                )
                ax = str((cov or {}).get("camera_axis") or "").strip()
                if ax:
                    previous_axes.append(ax)
                previous_focal = str((cov or {}).get("focal_character") or previous_focal or "")

                vp = str((cov or {}).get("viewpoint") or "")
                if vp:
                    previous_viewpoints.append(vp)
                    previous_viewpoint = vp
                else:
                    previous_viewpoint = previous_viewpoint or ""

                previous_look = str((cov or {}).get("look_axis") or previous_look or "")

                ep = str(shot.get("dsl", {}).get("end_pose") or shot.get("end_pose") or "")
                if ep:
                    previous_end_pose = ep

            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            dsl = shot.get("dsl")
            if not isinstance(dsl, dict) or not dsl:
                raise FilmSpecError(f"{shot_id} requires non-empty dsl object")
            # Motion language is required for I2V dynamics (camera + body)
            motion = dsl.get("motion")
            try:
                dsl["motion"] = validate_motion(motion, field=f"{shot_id}.dsl.motion")
            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            # Wave γ · drive beats default cut_on=mid_motion (kinetic, not settle-hold)
            try:
                from edit_policy import apply_shot_edit_rhythm_defaults

                apply_shot_edit_rhythm_defaults(shot)
            except Exception:
                pass
            duration = shot.get("duration_sec")
            if duration is None:
                duration_value = DEFAULT_DURATION_SEC
                shot["duration_sec"] = DEFAULT_DURATION_SEC
            else:
                try:
                    duration_value = float(duration)
                except (TypeError, ValueError) as exc:
                    raise FilmSpecError(f"{shot_id}.duration_sec must be a number") from exc
                if duration_value <= 0 or duration_value > 60:
                    raise FilmSpecError(f"{shot_id}.duration_sec must be > 0 and <= 60")
                shot["duration_sec"] = duration_value
            # S1 hard gate: VO estimate must fit the I2V plate (no loop-to-fill).
            est_vo = float(shot["est_vo_sec"])
            if est_vo > duration_value + VO_PACING_SLACK_SEC:
                raise FilmSpecError(
                    f"{shot_id} vo_pacing: est_vo_sec={est_vo} > duration_sec={duration_value} "
                    f"(slack {VO_PACING_SLACK_SEC}s). Shorten nar (≤{RECOMMENDED_NAR_CHARS} chars for 6s), "
                    f"set duration_sec to 10, or split into another shot — do not rely on stream_loop."
                )
            shots.append(shot)
    if not shots:
        raise FilmSpecError("film-spec requires at least one shot")

    # P2-10: vo_lint_strict — product genre or explicit flag elevates VO de-AI lint to hard
    if spec.get("vo_lint_strict") is True and _vo_lint_violations:
        codes = sorted({v.get("code", "VO_LINT") for v in _vo_lint_violations})
        raise FilmSpecError("vo_lint failed (vo_lint_strict): " + ",".join(codes))
    spec["_vo_lint_summary"] = {
        "ok": len(_vo_lint_violations) == 0,
        "violation_count": len(_vo_lint_violations),
        "violations": _vo_lint_violations,
        "note": "VO de-AI lint: brochure phrase / AI cadence / long sentence. "
        "Soft by default; vo_lint_strict raises.",
    }

    if mode == "dialogue_drama":
        on_camera = [s for s in shots if s.get("screen_mode") == "on_camera"]
        coverage = [
            s for s in shots if s.get("screen_mode") in {"reaction", "action_cover", "silence"}
        ]
        if len(on_camera) >= 2 and not coverage:
            raise FilmSpecError(
                "dialogue_drama requires a reaction/action_cover/silence shot; "
                "do not cut consecutive speaking close-ups only"
            )
        coverage_beats = {
            str(shot.get("beat_id") or "")
            for shot in coverage
            if str(shot.get("beat_id") or "").strip()
        }
        # Timed dialogue B-roll is coverage beneath its parent A-roll: it
        # replaces picture while retaining that line's dialogue/caption clock.
        # Treat it as beat coverage as well as legacy standalone cover shots.
        coverage_beats.update(
            str(shot.get("beat_id") or "")
            for shot in on_camera
            if shot.get("dialogue_broll") and str(shot.get("beat_id") or "").strip()
        )
        missing_beat_coverage = sorted(
            {
                str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "")
                for shot in on_camera
                if str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "")
                not in coverage_beats
            }
        )
        if missing_beat_coverage:
            raise FilmSpecError(
                "dialogue_drama requires reaction/action_cover/silence for every dialogue beat; "
                "missing=" + ",".join(missing_beat_coverage)
            )
        # Dialogue-first scene contract: every scene must put a speaking character
        # in frame at least once (on_camera or off_camera dialogue). Scenes made of
        # pure silence/coverage plates or narration-VO-only pictures are rejected —
        # narration is gap-only, never the primary voice of a scene.
        # Escape: scene {"silent_scene": true, "narration_reason": "..."} or spec-level
        # allow_silent_scenes:true.
        allow_silent_scenes = spec.get("allow_silent_scenes") is True
        has_scenes = isinstance(spec.get("scenes"), list) and bool(spec.get("scenes"))

        def _scene_dialogue_shots(scene: dict[str, Any]) -> list[dict[str, Any]]:
            scene_shots = scene.get("shots")
            if not isinstance(scene_shots, list):
                return []
            talking: list[dict[str, Any]] = []
            for scene_shot in scene_shots:
                if not isinstance(scene_shot, dict):
                    continue
                if str(scene_shot.get("screen_mode") or "") not in {"on_camera", "off_camera"}:
                    continue
                cues = scene_shot.get("audio_cues")
                if not isinstance(cues, list):
                    continue
                if any(
                    isinstance(cue, dict)
                    and cue.get("kind") == "voice"
                    and cue.get("line_type") == "dialogue"
                    and str(cue.get("spoken_text") or "").strip()
                    for cue in cues
                ):
                    talking.append(scene_shot)
            return talking

        scenes_without_dialogue: list[str] = []
        if has_scenes and not allow_silent_scenes:
            for scene_index, scene in enumerate(spec.get("scenes") or [], start=1):
                if not isinstance(scene, dict):
                    continue
                if scene.get("silent_scene") is True:
                    if str(scene.get("narration_reason") or "").strip():
                        continue
                    scenes_without_dialogue.append(
                        f"scene{scene_index}(id={scene.get('id') or scene_index}):"
                        "silent_scene_requires_narration_reason"
                    )
                    continue
                if not _scene_dialogue_shots(scene):
                    scenes_without_dialogue.append(
                        f"scene{scene_index}(id={scene.get('id') or scene_index})"
                    )
        consecutive = 0
        prior_speaker = ""
        for shot in shots:
            if shot.get("screen_mode") == "on_camera":
                speaker = str(shot.get("speaker") or "")
                consecutive = consecutive + 1 if speaker and speaker == prior_speaker else 1
                prior_speaker = speaker
                if consecutive >= 3:
                    raise FilmSpecError(
                        "dialogue_drama forbids three consecutive on_camera shots for the same speaker; "
                        "insert reaction/action_cover/silence"
                    )
            else:
                consecutive = 0
                prior_speaker = ""
        dialogue_sec = sum(
            float(cue.get("duration_sec") or 0)
            for shot in shots
            for cue in (shot.get("audio_cues") or [])
            if isinstance(cue, dict)
            and cue.get("kind") == "voice"
            and cue.get("line_type") == "dialogue"
        )
        narration_sec = sum(
            float(cue.get("duration_sec") or 0)
            for shot in shots
            for cue in (shot.get("audio_cues") or [])
            if isinstance(cue, dict)
            and cue.get("kind") == "voice"
            and cue.get("line_type") == "narration"
        )
        narration_ratio = narration_sec / max(dialogue_sec + narration_sec, 1.0)
        # Delivery Truth · zero_narration IRON (default on for dialogue_drama)
        zn = zero_narration_gate(spec, shots=shots)
        spec["_zero_narration"] = zn
        zero_strict = bool(zn.get("zero_narration_strict"))
        if zero_strict:
            narration_budget = 0.0
        else:
            try:
                narration_budget = float(spec.get("narration_budget_ratio") or 0.05)
            except (TypeError, ValueError):
                narration_budget = 0.05
            narration_budget = max(0.0, min(0.15, narration_budget))
        if not zn.get("ok"):
            raise FilmSpecError(
                f"NAR_BUDGET_VIOLATION: {zn.get('message') or 'zero narration strict failed'}"
            )
        # Legacy storyteller ban when IRON not escaped (zero_strict already covers)
        if zero_strict and spec.get("allow_storyteller_nar") is not True:
            for shot in shots:
                if not isinstance(shot, dict):
                    continue
                sid = str(shot.get("id") or "?")
                nar = str(shot.get("nar") or "").strip()
                if not nar:
                    continue
                cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
                has_dialogue_voice = any(
                    isinstance(c, dict)
                    and c.get("kind") == "voice"
                    and c.get("line_type") == "dialogue"
                    for c in cues
                ) or bool(str(shot.get("spoken_text") or "").strip())
                has_narration_voice = any(
                    isinstance(c, dict)
                    and c.get("kind") == "voice"
                    and c.get("line_type") == "narration"
                    for c in cues
                )
                if has_dialogue_voice:
                    continue
                if has_narration_voice and str(shot.get("narration_reason") or "").strip():
                    continue
                if (
                    str(shot.get("narration_reason") or "").strip()
                    and shot.get("silent_scene") is True
                ):
                    continue
                raise FilmSpecError(
                    f"NAR_BUDGET_VIOLATION: {sid}: dialogue_drama forbids third-person "
                    "storyteller nar as primary voice — use character dialogue, pure-visual "
                    "silence/action_cover, or escape zero_narration_strict:false / "
                    "allow_storyteller_nar:true"
                )
        spec["_dialogue_drama"] = {
            "on_camera_shots": len(on_camera),
            "coverage_shots": len(coverage),
            "scenes_without_dialogue": scenes_without_dialogue,
            "allow_silent_scenes": allow_silent_scenes,
            "coverage_beats": sorted(coverage_beats),
            "missing_beat_coverage": missing_beat_coverage,
            "dialogue_sec": round(dialogue_sec, 3),
            "narration_sec": round(narration_sec, 3),
            "narration_ratio": round(float(zn.get("ratio") or narration_ratio), 4),
            "narration_target_ratio": 0.0,
            "narration_budget_ratio": narration_budget,
            "zero_narration_strict": zero_strict,
            "coverage_ratio": round(
                sum(float(s.get("duration_sec") or 0) for s in coverage)
                / max(sum(float(s.get("duration_sec") or 0) for s in shots), 1.0),
                4,
            ),
            "coverage_targets": {
                "on_camera": "35-45%",
                "reaction": "20-25%",
                "action_cover": "about 20%",
                "space_or_silence": "10-15%",
            },
            "note": (
                "Cinema dialogue primary: speech=character Chinese mouth; no speech=pure picture. "
                + (
                    "Zero-narration IRON: nar hard cap 0%."
                    if zero_strict
                    else f"Narration gap-only; hard cap {narration_budget:.0%}."
                )
            ),
        }
        broll = iter_dialogue_broll(spec)
        spec["_dialogue_broll"] = {
            "enabled": bool(broll),
            "count": len(broll),
            "parent_shot_ids": [str(item.get("parent_shot_id") or "") for item in broll],
            "audio_policy": "carry_parent_dialogue",
            "note": "B-roll replaces only parent picture inside bounded cuts; dialogue/subtitle clocks stay on A-roll.",
        }
        if (
            not zero_strict
            and spec.get("narration_budget_strict") is not False
            and narration_ratio > narration_budget + 1e-9
        ):
            raise FilmSpecError(
                f"NAR_BUDGET_VIOLATION: dialogue_drama narration budget exceeded: "
                f"{narration_ratio:.0%} > {narration_budget:.0%} "
                f"(raise narration_budget_ratio or cut gap VO)"
            )

    # Aggregate VO budget report (non-blocking summary for agents / status)
    total_est = sum(float(s.get("est_vo_sec") or 0) for s in shots)
    long_recommended = [
        s["id"] for s in shots if len(str(s.get("nar") or "")) > RECOMMENDED_NAR_CHARS
    ]
    # Soft advisory: still surface shots that sit near the 6s plate edge.
    loop_risk = [
        s["id"]
        for s in shots
        if float(s.get("est_vo_sec") or 0) > LOOP_RISK_VO_SEC
        and float(s.get("duration_sec") or DEFAULT_DURATION_SEC) <= 6.5
    ]
    no_loop_beats = [
        s["id"]
        for s in shots
        if str(s.get("dramatic_function") or "") in NO_LOOP_DRAMATIC_FUNCTIONS
    ]
    # Scene-adaptive audio recipes (policy + per-shot recipe; soft degrade)
    try:
        caps = probe_caps_for_root(film_root)
        apply_audio_recipes_to_spec(
            spec,
            shots,
            lipsync_ready=bool(caps.get("lipsync_ready")),
            music_library=bool(caps.get("music_library")),
            sung_provider_ready=bool(caps.get("sung_provider_ready")),
        )
    except AudioRecipeError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Adult flesh SFX → sound_plan events (after voice_tracks auto sound_cues)
    try:
        heat_for_sfx = str(spec.get("heat_scale") or "").strip().lower() or None
        sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else None
        if sp is None and heat_for_sfx in {"max", "hot"}:
            sp = default_sound_plan_for_film(
                vo_mode=str(spec.get("vo_mode") or "storyteller"),
                tone=str((spec.get("director_intent") or {}).get("tone") or ""),
                title=str(spec.get("title") or ""),
                description=str(spec.get("description") or ""),
            )
        if isinstance(sp, dict):
            sp = inject_auto_sfx_if_empty(sp, shots, heat_scale=heat_for_sfx)
            sp = inject_sex_sfx_from_shots(sp, shots, heat_scale=heat_for_sfx)
            sp = inject_music_energy_spotting(sp, shots, heat_scale=heat_for_sfx)
            spec["sound_plan"] = sp
            if sp.get("_notes"):
                notes = list(spec.get("_sound_plan_notes") or [])
                for n in sp.get("_notes") or []:
                    if n not in notes:
                        notes.append(n)
                spec["_sound_plan_notes"] = notes
    except Exception as exc:  # noqa: BLE001 — soft
        notes = list(spec.get("_sound_plan_notes") or [])
        notes.append(f"sex_sfx inject soft-fail: {exc}")
        spec["_sound_plan_notes"] = notes

    # Author-omit tracking before edit_strategy / craft blocks.
    transition_sec_authored = "transition_sec" in spec and spec.get("transition_sec") is not None
    edit_craft_authored = isinstance(spec.get("edit_craft"), list) or isinstance(
        spec.get("edit_crafts"), list
    )
    if not transition_sec_authored:
        spec["transition_sec"] = DEFAULT_TRANSITION_SEC
    try:
        spec["transition_sec"] = normalize_transition_sec(spec.get("transition_sec"))
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Voice-coupled editorial strategy (after vocal_color exists)
    try:
        from edit_strategy import EditStrategyError, apply_edit_strategy_to_spec

        apply_edit_strategy_to_spec(spec)
        if not transition_sec_authored:
            spec["transition_sec"] = DEFAULT_TRANSITION_SEC
    except EditStrategyError as exc:
        raise FilmSpecError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — soft: never block write-spec
        notes = list(spec.get("_edit_strategy_errors") or [])
        notes.append(str(exc))
        spec["_edit_strategy_errors"] = notes

    spec["_vo_budget"] = {
        "max_nar_chars": MAX_NAR_CHARS,
        "recommended_nar_chars": RECOMMENDED_NAR_CHARS,
        "loop_risk_vo_sec": LOOP_RISK_VO_SEC,
        "vo_pacing_slack_sec": VO_PACING_SLACK_SEC,
        "shot_count": len(shots),
        "total_est_vo_sec": round(total_est, 2),
        "shots_over_recommended": long_recommended,
        "loop_risk_shots": loop_risk,
        "no_loop_beats": no_loop_beats,
        "note": (
            "Hard: est_vo_sec ≤ duration_sec+slack (vo_pacing). "
            "Prefer nar≤28 so final stretch uses loops=0. "
            "hook/action never stream_loop in final. Grow runtime by adding shots."
        ),
    }

    # Wave γ · edit rhythm: dialogue_drama visual_fit=vo; drive cut_on; anti-PPT note
    try:
        from edit_policy import (
            apply_film_edit_rhythm_defaults,
            default_visual_fit,
            lint_equal_duration_ppt,
        )

        rhythm = apply_film_edit_rhythm_defaults(spec)
        ppt = lint_equal_duration_ppt(
            shots,
            visual_fit=str(spec.get("visual_fit") or default_visual_fit(spec)),
        )
        if not ppt.get("ok"):
            notes = list(spec.get("_edit_rhythm_warnings") or [])
            for iss in ppt.get("issues") or []:
                notes.append(str(iss.get("message") or iss.get("code")))
            spec["_edit_rhythm_warnings"] = notes
            rhythm = {**(spec.get("_edit_rhythm") or rhythm), "ppt_lint": ppt}
            spec["_edit_rhythm"] = rhythm
    except Exception as exc:  # noqa: BLE001
        spec["_edit_rhythm_errors"] = [str(exc)[:200]]

    # Wave 2 · dialogue_audio_lane native|post_tts|silence on spoken shots
    try:
        from final.native_audio import apply_film_dialogue_audio_lanes

        apply_film_dialogue_audio_lanes(spec)
    except Exception as exc:  # noqa: BLE001
        spec["_dialogue_audio_lanes_errors"] = [str(exc)[:200]]

    # Wave δ · 5-Track cinema mix defaults (DX/FX/BG/MX/SUB + -16 LUFS)
    try:
        from five_track import ensure_five_track_defaults

        ft = ensure_five_track_defaults(spec)
        if ft.get("enabled"):
            spec["_five_track"] = ft
    except Exception as exc:  # noqa: BLE001
        spec["_five_track_errors"] = [str(exc)[:200]]

    # Validate or auto-suggest story join intents now that shot count is known
    expected = max(0, len(shots) - 1)
    chain_modes: list[str] = []
    cut_ons: list[str] = []
    scene_ids: list[str] = []
    # rebuild scene index per shot (scenes order)
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sid_label = str(scene.get("id") or scene.get("title") or f"scene{si}")
        for sh in scene.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            # only count shots that made it into validated `shots` list by id
            pass
    # Prefer validated shots list for chain/cut; scene membership from original scenes
    shot_to_scene: dict[str, str] = {}
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sid_label = str(scene.get("id") or scene.get("title") or f"scene{si}")
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                shot_to_scene[str(sh["id"])] = sid_label
    for s in shots:
        dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
        chain_modes.append(str((dsl or {}).get("chain_mode") or "").strip().lower())
        cut_ons.append(str((dsl or {}).get("cut_on") or "").strip().lower())
        scene_ids.append(shot_to_scene.get(str(s.get("id") or ""), "scene0"))

    # Editorial craft plan (资深剪辑语法) — always materialize for agent visibility
    beats = [str(s.get("dramatic_function") or "bridge") for s in shots]
    flu = str(spec.get("transition_fluency") or "auto")
    # cinematic fluency uses craft-rich suggestions (same catalog, anti soft-run)
    craft_flu = "cinematic" if flu in {"silk", "cinematic", "auto"} else flu
    raw_crafts = spec.get("edit_craft") or spec.get("edit_crafts")
    crafts: list[str] = []
    focals_for_craft = [
        str(
            (
                (s.get("dsl") or {}).get("focal_character")
                if isinstance(s.get("dsl"), dict)
                else None
            )
            or s.get("focal_character")
            or "hero"
        )
        for s in shots
    ]
    viewpoints_for_craft = [
        str(
            ((s.get("dsl") or {}).get("viewpoint") if isinstance(s.get("dsl"), dict) else None)
            or s.get("viewpoint")
            or "objective"
        )
        for s in shots
    ]
    if raw_crafts is not None:
        if not isinstance(raw_crafts, list) or len(raw_crafts) != expected:
            raise FilmSpecError(
                f"edit_craft length must be n_shots-1={expected}; got "
                f"{len(raw_crafts) if isinstance(raw_crafts, list) else type(raw_crafts)}"
            )
        try:
            crafts = [
                normalize_edit_craft(x, field=f"edit_craft[{i}]") for i, x in enumerate(raw_crafts)
            ]
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        spec["_edit_craft_source"] = "author" if edit_craft_authored else "craft_suggest"
    elif expected > 0:
        try:
            crafts = suggest_edit_crafts(
                beats,
                chain_modes=chain_modes,
                cut_ons=cut_ons,
                scene_ids=scene_ids,
                fluency=craft_flu if flu != "punchy" else "punchy",
                focals=focals_for_craft,
                viewpoints=viewpoints_for_craft,
            )
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        spec["_edit_craft_source"] = "craft_suggest"
    if crafts:
        # continue seams must stay HARD-intent crafts (smash/insert/montage ok as labels)
        hard_family = {
            "match_cut",
            "cut_on_action",
            "smash_cut",
            "contrast_cut",
            "insert_cut",
            "montage_jump",
        }
        for i, c in enumerate(crafts):
            next_chain = chain_modes[i + 1] if i + 1 < len(chain_modes) else ""
            if next_chain in {"continue", "match", "match_cut", "byte"} and c not in hard_family:
                crafts[i] = (
                    "cut_on_action"
                    if (cut_ons[i + 1] if i + 1 < len(cut_ons) else "")
                    in {"mid_motion", "mid-action", "action"}
                    else "match_cut"
                )
        spec["edit_craft"] = crafts
        spec["_edit_craft_plan"] = [
            {
                "join_index": i,
                "craft": c,
                "why": _CRAFT_WHY.get(c, ""),
                "intent": edit_crafts_to_intents([c])[0],
            }
            for i, c in enumerate(crafts)
        ]

    # rebound after provider peel (W2) — same validation as former inlined block
    raw_intents = spec.get("transition_intents")
    if raw_intents is not None and not isinstance(raw_intents, list):
        raise FilmSpecError("transition_intents must be an array of hard|soft|hold")
    raw_styles = spec.get("transition_styles")
    if raw_styles is not None and not isinstance(raw_styles, list):
        raise FilmSpecError("transition_styles must be an array of xfade style names")

    if raw_intents is not None:
        if len(raw_intents) != expected:
            raise FilmSpecError(
                f"transition_intents length must be n_shots-1={expected}; got {len(raw_intents)}"
            )
        try:
            author_intents = [
                normalize_transition_intent(x, field=f"transition_intents[{i}]")
                for i, x in enumerate(raw_intents)
            ]
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        # continue seams always hard — even if author wrote soft/hold (男娘咖啡厅)
        fixed, fix_notes = enforce_continue_hard_joins(author_intents, chain_modes)
        spec["transition_intents"] = fixed
        spec["_transition_intents_source"] = "author"
        if fix_notes:
            spec["_transition_continue_hard_fixes"] = fix_notes
    elif expected > 0:
        try:
            if crafts:
                auto = edit_crafts_to_intents(crafts)
            else:
                auto = suggest_transition_intents(
                    beats,
                    chain_modes=chain_modes,
                    fluency=flu,
                    cut_ons=cut_ons,
                    scene_ids=scene_ids,
                )
            fixed, fix_notes = enforce_continue_hard_joins(auto, chain_modes)
            spec["transition_intents"] = [
                normalize_transition_intent(x, field=f"transition_intents[{i}]")
                for i, x in enumerate(fixed)
            ]
        except PolicyError as exc:
            raise FilmSpecError(str(exc)) from exc
        spec["_transition_intents_source"] = "edit_craft" if crafts else "beat_suggest"
        if fix_notes:
            spec["_transition_continue_hard_fixes"] = fix_notes

    # Dual caption soft report (not hard fail — agent can fill nar_en later)
    cap_mode = str(spec.get("caption_mode") or "zh")
    if cap_mode == "zh_en":
        missing_en = [str(s.get("id")) for s in shots if not str(s.get("nar_en") or "").strip()]
        spec["_caption_mode_report"] = {
            "mode": "zh_en",
            "missing_nar_en": missing_en,
            "ok": len(missing_en) == 0,
            "note": "zh_en designed-post needs shot.nar_en for dual lines; agent fills EN",
        }
    else:
        spec["_caption_mode_report"] = {"mode": cap_mode, "ok": True}

    # Per-join xfade styles (anti soft-soup of only fade)
    intents_for_styles = spec.get("transition_intents")
    if expected > 0 and isinstance(intents_for_styles, list):
        if raw_styles is not None:
            try:
                spec["transition_styles"] = normalize_transition_styles(
                    list(raw_styles),
                    n_joins=expected,
                    fallback=str(spec.get("transition_style") or "fade"),
                )
            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            spec["_transition_styles_source"] = "author"
        else:
            try:
                auto_styles = suggest_transition_styles(
                    [str(x) for x in intents_for_styles],
                    dramatic_functions=beats,
                    edit_crafts=crafts if crafts else None,
                )
                spec["transition_styles"] = normalize_transition_styles(
                    auto_styles,
                    n_joins=expected,
                    fallback=str(spec.get("transition_style") or "fade"),
                )
            except PolicyError as exc:
                raise FilmSpecError(str(exc)) from exc
            spec["_transition_styles_source"] = "edit_craft" if crafts else "beat_suggest"

    # Every seam is an explicit operation, including a hard cut.  This is the
    # contract consumed by designed post and the final-delivery receipt.
    raw_ops = spec.get("transition_ops")
    if raw_ops is not None and not isinstance(raw_ops, list):
        raise FilmSpecError("transition_ops must be an array")
    try:
        resolved_intents = [str(x) for x in spec.get("transition_intents") or []]
        raw_join_secs = spec.get("join_transition_secs")
        if isinstance(raw_join_secs, list):
            operation_secs = list(raw_join_secs)
        else:
            # edit_strategy=off still receives a complete per-seam operation.
            operation_secs = [
                0.0 if intent == "hard" else float(spec["transition_sec"])
                for intent in resolved_intents
            ]
        spec["transition_ops"] = build_transition_operations(
            shots,
            crafts=[str(x) for x in spec.get("edit_craft") or []],
            intents=resolved_intents,
            styles=[str(x) for x in spec.get("transition_styles") or []],
            durations=operation_secs,
            authored=list(raw_ops) if raw_ops is not None else None,
        )
        spec["_transition_ops_source"] = "author_overlay" if raw_ops is not None else "edit_craft"
    except TransitionOperationError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Layer identity soft report: T2V/env beds must not claim hero face lock
    layer_issues: list[dict[str, Any]] = []
    hero_n = sum(1 for s in shots if s.get("shot_role") == "hero")
    env_n = sum(1 for s in shots if s.get("shot_role") in {"env", "bridge", "insert"})
    for s in shots:
        sid = str(s.get("id") or "")
        role = str(s.get("shot_role") or "hero")
        dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
        if role == "hero":
            # hero should have identity anchors for agent
            if not str(dsl.get("subject") or "").strip() and not dsl.get("cast"):
                layer_issues.append(
                    {
                        "code": "HERO_MISSING_IDENTITY_ANCHOR",
                        "severity": "warning",
                        "shot_id": sid,
                        "message": (
                            f"{sid} shot_role=hero but no dsl.cast/subject — "
                            "lock cast master before I2V"
                        ),
                    }
                )
        elif role in {"env", "insert", "bridge"}:
            # warn if author writes face-fill language on env bed
            blob = " ".join(
                str(dsl.get(k) or "") for k in ("subject", "action", "motion", "story_beat")
            ).lower()
            if any(
                k in blob
                for k in (
                    "close-up face",
                    "portrait face",
                    "fills frame",
                    "hero face",
                    "cast master",
                )
            ):
                layer_issues.append(
                    {
                        "code": "ENV_BED_FACE_LANGUAGE",
                        "severity": "warning",
                        "shot_id": sid,
                        "message": (
                            f"{sid} shot_role={role} looks face-centric — "
                            "use hero I2V for identity; keep LTX T2V face-free"
                        ),
                    }
                )
    spec["_layer_report"] = {
        "hero_shots": hero_n,
        "env_synth_shots": env_n,
        "issues": layer_issues,
        "ok": len(layer_issues) == 0,
        "note": (
            "hero→cast still + I2V (Seedance/Grok); "
            "env/bridge/insert→LTX T2V beds for splice (no face import)"
        ),
    }
    return shots
