"""Soft production gates tail for film_spec validation (W2 peel).

Continuity / stance / performance / scene board / motion / meaning / audio / consistency.
Structure-only. Uses existing lint helpers only (W2.4: no dual implementation).
"""

from __future__ import annotations

from typing import Any

from content_channels import lint_content_channels
from continuity import (
    lint_continuity,
    lint_frame_chain,
    lint_meaningful_motion,
    lint_production_consistency,
    lint_transition_styles,
    lint_vo_motion_link,
)
from continuity_chain import is_long_form
from dialogue_contracts import summarize_dialogue_contracts
from framing_lint import lint_composition_rules, lint_framing_iron, lint_vertical_safe_area
from edit_policy import lint_character_stance
from plan.film_spec_lints import (
    FilmSpecError,
    lint_director_board,
    lint_performance,
)
from rhythm import lint_rhythm
from narrative_timeline import (
    NarrativeTimelineError,
    validate_linear_narration,
    validate_sfx_scene_bindings,
)

try:
    from dialogue_speaker_frame_gate import lint_dialogue_speaker_frame
except ImportError:  # pragma: no cover
    from narrative.dialogue_speaker_frame_gate import lint_dialogue_speaker_frame  # type: ignore

try:
    from dramatic_meaning import lint_dramatic_meaning
except ImportError:  # pragma: no cover
    from plan.dramatic_meaning import lint_dramatic_meaning  # type: ignore


def apply_soft_production_gates(
    spec: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    enforce_narrative_timeline: bool = False,
) -> None:
    """Attach soft lint reports; raise only when corresponding *_strict flags set."""
    scenes = spec.get("scenes") if isinstance(spec.get("scenes"), list) else []
    mode = str(spec.get("vo_mode") or "storyteller").lower()
    target_duration = spec.get("target_duration") or spec.get("duration_sec")
    # Continuity lint (non-strict by default; attach report on spec)
    cont = lint_continuity(shots)
    spec["_continuity_lint"] = {
        "ok": cont["ok"],
        "codes": cont["codes"],
        "error_count": cont["error_count"],
        "warning_count": cont["warning_count"],
        "issues": cont["issues"],
    }
    if spec.get("continuity_strict") is True and not cont["ok"]:
        raise FilmSpecError(
            "continuity lint failed (continuity_strict): " + ",".join(cont["codes"])
        )

    # Character stance / multi-POV (soft; character-stance.md)
    stance = lint_character_stance(shots)
    spec["_character_stance"] = {
        "ok": stance.get("ok"),
        "codes": stance.get("codes"),
        "warning_count": stance.get("warning_count"),
        "issues": stance.get("issues"),
        "viewpoint_set": stance.get("viewpoint_set"),
        "focal_set": stance.get("focal_set"),
        "note": (
            "Soft: rotate viewpoint (ots/reverse/reaction/pov); "
            "reaction may flip focal_character; reverse prefers focal shift. "
            "See references/character-stance.md"
        ),
    }
    if spec.get("stance_strict") is True and not stance.get("ok"):
        raise FilmSpecError(
            "character stance lint failed (stance_strict): " + ",".join(stance.get("codes") or [])
        )

    # Performance / subtext (soft; performance_strict raises) — the director's
    # answer to "the camera moves, but what is the character's interior A→B?"
    # Mirrors drama-graph SHOT_PERFORMANCE_MISSING so the production contract
    # and canonical graph share one standard.
    perf = lint_performance(shots)
    spec["_performance_lint"] = {
        "ok": perf["ok"],
        "codes": perf["codes"],
        "warning_count": perf["warning_count"],
        "issues": perf["issues"],
        "note": (
            "Soft: hero shots should carry subtext / playable_action / body_state. "
            "I2V moves bodies; performance intent makes them act. "
            "Set performance_strict=true to hard-fail. See principles.md P0/P4"
        ),
    }
    if spec.get("performance_strict") is True and not perf["ok"]:
        raise FilmSpecError(
            "performance lint failed (performance_strict): " + ",".join(perf["codes"])
        )

    # Director decision board per scene (soft; scene_strict raises) — mirrors
    # drama-graph beat.director_board. A scene without authored emotional_turn /
    # audience_question / coverage_strategy / cut_intent has been pre-shot
    # without a director's pass.
    board = lint_director_board(scenes)
    spec["_director_board_lint"] = {
        "ok": board["ok"],
        "codes": board["codes"],
        "warning_count": board["warning_count"],
        "issues": board["issues"],
        "note": (
            "Soft: each scene should author director_board (emotional_turn / "
            "audience_question / coverage_strategy / cut_intent). "
            "Set scene_strict=true to require approval_state=approved before bulk."
        ),
    }
    if spec.get("scene_strict") is True and not board["ok"]:
        raise FilmSpecError(
            "director board lint failed (scene_strict): " + ",".join(board["codes"])
        )

    # VO–motion link / anti-fatigue (soft; lessons-2026-07-17-vo-motion-link)
    intents = spec.get("transition_intents")
    if not isinstance(intents, list):
        intents = None
    vml = lint_vo_motion_link(shots, transition_intents=intents)
    styles_for_lint = spec.get("transition_styles")
    if isinstance(styles_for_lint, list):
        stl = lint_transition_styles(
            [str(x) for x in styles_for_lint],
            join_intents=[str(x) for x in intents] if intents else None,
        )
        if stl.get("issues"):
            vml = {
                **vml,
                "issues": list(vml.get("issues") or []) + list(stl.get("issues") or []),
                "codes": sorted(set(vml.get("codes") or []) | set(stl.get("codes") or [])),
                "warning_count": int(vml.get("warning_count") or 0)
                + int(stl.get("warning_count") or 0),
                "ok": bool(vml.get("ok")) and bool(stl.get("ok")),
            }
    spec["_vo_motion_link"] = {
        "ok": vml["ok"],
        "codes": vml["codes"],
        "warning_count": vml["warning_count"],
        "issues": vml["issues"],
        "note": (
            "Soft: primary action leads micro fillers; rotate camera_axis; "
            "continue joins force hard; avoid SOFT_SOUP / STYLE_SOUP / CAMERA_AXIS_FLAT. "
            "See lessons-2026-07-20-transition-motion-v2.md"
        ),
    }
    # Meaningful motion: dynamics must carry beat-readable story
    mm = lint_meaningful_motion(shots)
    spec["_meaningful_motion"] = {
        "ok": mm["ok"],
        "codes": mm["codes"],
        "warning_count": mm["warning_count"],
        "issues": mm["issues"],
        "note": (
            "Soft: each shot motion must answer the beat's story question "
            "(not aesthetic blink/push-in only). Prefer dsl.visible_change + story_beat. "
            "See references/lessons-2026-07-20-meaningful-motion.md"
        ),
    }
    if spec.get("meaningful_motion_strict") is True and mm["warning_count"] > 0:
        raise FilmSpecError(
            "meaningful motion lint failed (meaningful_motion_strict): "
            + ",".join(mm["codes"] or ["MOTION"])
        )

    # Dramatic meaning stack (shot / motion / dialogue purpose / emotional_arc).
    # Report always written; fail-closed by default (every genre pack) when
    # meaning_gate_enabled. write-spec also hard-fails via cinematic_audit
    # regardless of this flag.
    from dramatic_meaning import lint_dramatic_meaning, meaning_gate_enabled

    meaning = lint_dramatic_meaning(spec, shots=shots)
    spec["_dramatic_meaning"] = {
        "ok": meaning.get("ok"),
        "enabled": meaning_gate_enabled(spec),
        "codes": meaning.get("codes"),
        "error_count": meaning.get("error_count"),
        "issues": meaning.get("issues"),
        "parts": {
            key: {
                "ok": part.get("ok"),
                "codes": part.get("codes"),
                "error_count": part.get("error_count"),
            }
            for key, part in (meaning.get("parts") or {}).items()
            if isinstance(part, dict)
        },
        "checked": meaning.get("checked"),
        "note": meaning.get("note"),
    }
    if meaning_gate_enabled(spec) and not meaning.get("ok"):
        raise FilmSpecError(
            "dramatic meaning gate failed (dramatic_meaning_strict): "
            + ",".join(meaning.get("codes") or ["SHOT_MEANING_EMPTY"])
        )

    # I2.3 · speaker-frame hard on max dialogue_drama (write-spec fail-closed)
    try:
        from dialogue_speaker_frame_gate import (
            lint_dialogue_speaker_frame,
            speaker_frame_hard_enabled,
        )

        sf_rep = lint_dialogue_speaker_frame(spec)
        sf_hard = speaker_frame_hard_enabled(spec)
        bad_sf = list(sf_rep.get("violations") or []) + list(sf_rep.get("window_violations") or [])
        spec["_speaker_frame"] = {
            "ok": bool(sf_rep.get("ok")),
            "hard": sf_hard,
            "violation_count": len(bad_sf),
            "codes": sorted(
                {str(v.get("code")) for v in bad_sf if isinstance(v, dict) and v.get("code")}
            ),
        }
        if sf_hard and bad_sf:
            codes = sorted({str(v.get("code")) for v in bad_sf if v.get("code")})
            raise FilmSpecError(
                "speaker-frame gate failed (dialogue_drama max/adult): "
                + ",".join(codes or ["SPEAKER_FRAME"])
                + " — speaker must match picture subject; escape speaker_frame_strict:false"
            )
    except FilmSpecError:
        raise
    except Exception as exc:  # noqa: BLE001
        spec["_speaker_frame"] = {"ok": True, "skipped": True, "error": str(exc)[:160]}

    # Shot-local audio is additive for legacy projects, strict for new timed plans.
    try:
        from audio_cues import AudioCueError, validate_audio_cues

        spec["_audio_cues"] = validate_audio_cues(
            shots, strict=bool(spec.get("audio_cues_strict")) or mode == "dialogue_drama"
        )
    except AudioCueError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Content channels: keep spoken text, visible performance and motion apart.
    channel_report = lint_content_channels(shots)
    spec["_content_channels"] = channel_report
    if spec.get("content_channels_strict") is True and not channel_report["ok"]:
        raise FilmSpecError(
            "content channel lint failed (content_channels_strict): "
            + ",".join(channel_report["codes"] or ["CONTENT_CHANNEL"])
        )

    # Director rhythm: hook timing, coverage repetition, size pressure, button.
    rhythm = lint_rhythm(shots, target_duration=float(target_duration) if target_duration else None)
    _rhythm_warn = int(rhythm.get("warning_count") or len(rhythm.get("issues") or []))
    spec["_rhythm"] = {
        "ok": rhythm.get("ok", True),
        "codes": rhythm.get("codes") or [],
        "warning_count": _rhythm_warn,
        "issues": rhythm.get("issues") or [],
        "note": "Advisory by default; set rhythm_strict=true after director grammar is authored.",
    }
    if spec.get("rhythm_strict") is True and _rhythm_warn > 0:
        raise FilmSpecError(
            "rhythm lint failed (rhythm_strict): " + ",".join(rhythm["codes"] or ["RHYTHM"])
        )

    # Keep general schema/craft validation usable by authoring tools. Timeline
    # playback is enforced at write-spec and render boundaries, where every VO
    # line is actually committed to production.
    if enforce_narrative_timeline:
        try:
            validate_linear_narration(
                shots,
                vo_mode=str(spec["vo_mode"]),
                dialogue_spoken_lang=str(
                    spec.get("dialogue_spoken_lang")
                    or (spec.get("voice_policy") or {}).get("dialogue_spoken_lang")
                    or "zh"
                ),
                narration_spoken_lang=str(
                    spec.get("narration_spoken_lang")
                    or (spec.get("voice_policy") or {}).get("narration_spoken_lang")
                    or "zh"
                ),
            )
            validate_sfx_scene_bindings(spec.get("sound_plan"), shots)
        except NarrativeTimelineError as exc:
            raise FilmSpecError(f"narrative timeline invalid: {exc}") from exc
    # Frame chain (soft; lessons-2026-07-20-frame-chain) — soft/hold joins need end→start poses
    fch = lint_frame_chain(shots, transition_intents=intents)
    spec["_frame_chain"] = {
        "ok": fch["ok"],
        "codes": fch["codes"],
        "warning_count": fch["warning_count"],
        "issues": fch["issues"],
        "note": (
            "Soft/hold: end_pose→start_pose; continue join next keyframe MUST byte-reuse "
            "prev approved last frame (extract-frame --promote-keyframe). "
            "Do NOT restart from cast. Forbidden: dissolve/freeze/reverse/insert to hide breaks. "
            "Long-form requires continuity_chain.md — see references/continuity_chain.md"
        ),
    }
    if spec.get("frame_chain_strict") is True and fch["warning_count"] > 0:
        raise FilmSpecError(
            "frame chain lint failed (frame_chain_strict): "
            + ",".join(fch["codes"] or ["FRAME_CHAIN"])
        )
    # Long-form flag for agents (doc creation happens in write-spec CLI with root path)
    spec["_long_form"] = is_long_form(spec, shots)
    if spec.get("vo_motion_strict") is True and vml["warning_count"] > 0:
        raise FilmSpecError(
            "vo_motion_link lint failed (vo_motion_strict): " + ",".join(vml["codes"])
        )

    # A clipped head is never a deliverable state, so this is not opt-in.
    frm = lint_framing_iron(shots)
    spec["_framing_lint"] = {
        "ok": frm["ok"],
        "codes": frm["codes"],
        "warning_count": frm["warning_count"],
        "error_count": frm["error_count"],
        "issues": frm["issues"],
        "note": frm.get("note"),
    }
    if not frm["ok"]:
        raise FilmSpecError(
            "framing iron lint failed (full head + headroom required): "
            + ",".join(frm["codes"] or ["HEAD_CROP"])
        )

    # Production consistency P2-2~P2-6 (wardrobe/hair/makeup/light/rhythm/lipsync/voice drift)
    # Soft by default; production_consistency_strict raises. bible=spec so cast_locks/
    # hair_swatches/makeup/wardrobe_variants on spec (often mirrored from style-bible) are checked.
    pcr = lint_production_consistency(shots, bible=spec, spec=spec)
    spec["_production_consistency"] = {
        "ok": pcr["ok"],
        "codes": pcr["codes"],
        "warning_count": pcr["warning_count"],
        "error_count": pcr["error_count"],
        "issues": pcr["issues"],
        "note": pcr.get("note"),
    }
    if spec.get("production_consistency_strict") is True and not pcr["ok"]:
        raise FilmSpecError(
            "production consistency lint failed (production_consistency_strict): "
            + ",".join(pcr["codes"])
        )

    safe_area = lint_vertical_safe_area(shots)
    spec["_vertical_safe_area"] = {
        "ok": safe_area["ok"],
        "codes": safe_area["codes"],
        "warning_count": safe_area["warning_count"],
        "issues": safe_area["issues"],
        "note": "Declare platform UI, subtitle, subject and prop-safe zones for 9:16 shots.",
    }
    if spec.get("vertical_safe_area_strict") is True and safe_area["warning_count"] > 0:
        raise FilmSpecError(
            "vertical safe-area lint failed (vertical_safe_area_strict): "
            + ",".join(safe_area["codes"] or ["VERTICAL_SAFE_AREA"])
        )

    # Composition rules P1-7 (180° axis / 30° / eyeline / size progression)
    # Soft by default; composition_strict raises.
    compr = lint_composition_rules(shots)
    spec["_composition_rules"] = {
        "ok": compr["ok"],
        "codes": compr["codes"],
        "warning_count": compr["warning_count"],
        "error_count": compr["error_count"],
        "issues": compr["issues"],
        "note": compr.get("note"),
    }
    if spec.get("composition_strict") is True and not compr["ok"]:
        raise FilmSpecError(
            "composition rules lint failed (composition_strict): " + ",".join(compr["codes"])
        )

    # Dialogue contract P1-8 (timing/origin/lipsync truth)
    # Each shot may carry dialogue_contracts[]; validate each and collect errors.
    # Soft by default; dialogue_contract_strict raises.
    dialogue_contracts = summarize_dialogue_contracts(shots)
    spec["_dialogue_contracts"] = {
        **dialogue_contracts,
        "note": "P1-8: dialogue timing window, audio origin, lipsync truth. Soft by default.",
    }
    if spec.get("dialogue_contract_strict") is True and dialogue_contracts["errors"]:
        codes = dialogue_contracts["codes"]
        raise FilmSpecError(
            "dialogue contract validation failed (dialogue_contract_strict): " + ",".join(codes)
        )

