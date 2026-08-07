#!/usr/bin/env python3
"""Film-spec validation leaf (M1 peel · 2026-08-06).

Public entry remains ``film_spec.validate_film_spec`` via re-export.
Orchestrator only: provider → body (BGM/shots/edit) → soft gates → heat.
"""

from __future__ import annotations

from typing import Any

from dialogue_broll import iter_dialogue_broll

try:
    from plan.film_spec_constants import *  # noqa: F403
except ImportError:  # pragma: no cover
    from film_spec_constants import *  # type: ignore  # noqa: F403
from plan.film_spec_lints import (  # noqa: F401
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


def validate_film_spec(
    spec: dict[str, Any],
    *,
    assign_missing_ids: bool,
    film_root: Any | None = None,
    enforce_narrative_timeline: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(spec, dict):
        raise FilmSpecError("film-spec must be a JSON object")
    _required_text(spec.get("title"), field="title")
    mode = _required_text(spec.get("vo_mode"), field="vo_mode").lower()
    if mode not in VO_MODES:
        raise FilmSpecError(f"film-spec vo_mode must be one of {sorted(VO_MODES)}")
    spec["vo_mode"] = mode
    if mode != "dialogue_drama" and iter_dialogue_broll(spec):
        raise FilmSpecError("dialogue_broll is only supported when vo_mode=dialogue_drama")
    if mode == "dialogue_drama":
        dlang = str(spec.get("dialogue_spoken_lang") or "zh").lower()
        if dlang in {"ja", "jp", "japanese"}:
            raise FilmSpecError(
                "Japanese dialogue is retired; dialogue_drama requires dialogue_spoken_lang=zh"
            )
        if dlang not in {"zh", "cn", "chinese", "zh-cn", "zh_cn"}:
            raise FilmSpecError("dialogue_drama requires dialogue_spoken_lang=zh (Chinese-only)")
        spec["dialogue_spoken_lang"] = "zh"
        if str(spec.get("narration_spoken_lang") or "zh").lower() != "zh":
            raise FilmSpecError("dialogue_drama requires narration_spoken_lang=zh")
        spec["narration_spoken_lang"] = "zh"
        if not str(spec.get("caption_lang") or "").strip():
            spec["caption_lang"] = "zh"
    validate_director_intent(spec)
    if mode == "dialogue_drama":
        # v2.34 dialogue-first scene contract gate (early): every scene must put a
        # speaking character in frame at least once (on_camera/off_camera dialogue cue
        # with non-empty spoken_text). Scenes that only carry silence, coverage or
        # pure narration VO are rejected — narration stays gap-only, never the
        # primary voice of a scene. Escapes: scene {"silent_scene": true,
        # "narration_reason": "..."} for a justified gap scene, or spec-level
        # allow_silent_scenes:true.
        allow_silent_scenes_early = spec.get("allow_silent_scenes") is True
        scenes_early = spec.get("scenes")
        if not allow_silent_scenes_early and isinstance(scenes_early, list) and scenes_early:
            scenes_without_dialogue_early: list[str] = []
            for scene_index, scene in enumerate(scenes_early, start=1):
                if not isinstance(scene, dict):
                    continue
                if scene.get("silent_scene") is True:
                    if not str(scene.get("narration_reason") or "").strip():
                        scenes_without_dialogue_early.append(
                            f"scene{scene_index}(id={scene.get('id') or scene_index}):"
                            f"silent_scene_requires_narration_reason"
                        )
                    continue
                scene_shots = scene.get("shots")
                if not isinstance(scene_shots, list):
                    continue
                has_dialogue = False
                for scene_shot in scene_shots:
                    if not isinstance(scene_shot, dict):
                        continue
                    if str(scene_shot.get("screen_mode") or "") not in {
                        "on_camera",
                        "off_camera",
                    }:
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
                        has_dialogue = True
                        break
                if not has_dialogue:
                    scenes_without_dialogue_early.append(
                        f"scene{scene_index}(id={scene.get('id') or scene_index})"
                    )
            if scenes_without_dialogue_early:
                raise FilmSpecError(
                    "dialogue_drama requires dialogue in every scene — no narration-only "
                    "or silence-only scenes: "
                    + "; ".join(scenes_without_dialogue_early)
                    + ". Give the scene at least one on_camera/off_camera character "
                    "dialogue cue with visible speaking character. Escapes: scene "
                    "{'silent_scene': true, 'narration_reason': '...'} for a justified "
                    "gap scene, or spec-level allow_silent_scenes:true."
                )
    tts_backend = spec.get("tts_backend", "auto")
    if not isinstance(tts_backend, str) or tts_backend.lower() not in TTS_BACKENDS:
        raise FilmSpecError(f"film-spec tts_backend must be one of {sorted(TTS_BACKENDS)}")
    spec["tts_backend"] = tts_backend.lower()
    # 中文说书默认钉 MiMo；缺 key 时显式失败，避免静默换声线或 provider。
    if mode in ("storyteller", "hybrid") and spec["tts_backend"] == "auto":
        spec["tts_backend"] = "mimo"
        notes = list(spec.get("_tts_notes") or [])
        notes.append("auto→mimo for storyteller/hybrid (中文说书默认；显式 edge/fish/… 可覆盖)")
        spec["_tts_notes"] = notes
    # I2V / H3 / transition defaults (W2 leaf)
    try:
        from plan.film_spec_validate_provider import apply_provider_and_transition_defaults
    except ImportError:  # pragma: no cover
        from film_spec_validate_provider import apply_provider_and_transition_defaults
    apply_provider_and_transition_defaults(spec)

    # BGM + shot loop + edit craft (W2 residual leaf)
    try:
        from plan.film_spec_validate_body import apply_bgm_shots_and_edit_body
    except ImportError:  # pragma: no cover
        from film_spec_validate_body import apply_bgm_shots_and_edit_body
    shots = apply_bgm_shots_and_edit_body(
        spec,
        mode=mode,
        assign_missing_ids=assign_missing_ids,
        film_root=film_root,
    )

    # Soft production gates (W2 leaf — uses film_spec_lints / continuity helpers only)
    try:
        from plan.film_spec_validate_soft_gates import apply_soft_production_gates
    except ImportError:  # pragma: no cover
        from film_spec_validate_soft_gates import apply_soft_production_gates
    apply_soft_production_gates(
        spec, shots, enforce_narrative_timeline=enforce_narrative_timeline
    )

    # Heat + cast + adult sensory (W2 leaf)
    try:
        from plan.film_spec_validate_heat import apply_heat_cast_and_adult_tail
    except ImportError:  # pragma: no cover
        from film_spec_validate_heat import apply_heat_cast_and_adult_tail

    return apply_heat_cast_and_adult_tail(spec, shots, film_root=film_root)
