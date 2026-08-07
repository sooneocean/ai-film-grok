"""write-spec CLI — extracted from aifilm_grok (public command unchanged).

Includes legacy film-spec compatibility projectors used only by write-spec.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from continuity import lint_continuity
from continuity_chain import init_chain_doc, is_long_form
from film_spec import FilmSpecError, validate_film_spec
from prompt_injector import PromptConflictError, PromptInjector
from util import require_json as read_json
from util import sha256_file, write_json
from util.errors import FilmError
from visual_bible import load_bible


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def add_write_spec_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ws = sub.add_parser("write-spec", help="Validate and write film-spec + seed timeline")
    ws.add_argument("--root", required=True)
    ws.add_argument("--spec", help="Path to film-spec JSON (default root/film-spec.json)")


def _compatibility_vo_mode(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill missing vo_mode with cinema dialogue primary chain (Chinese spoken)."""
    if str(spec.get("vo_mode") or "").strip():
        return spec
    shots = [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]
    reason = "inferred_dialogue_drama_default"
    if shots and all(shot.get("silent") is True and not shot.get("dialogue") for shot in shots):
        reason = "inferred_dialogue_drama_zh_from_explicit_silent_shots"
    spec = dict(spec)
    spec["vo_mode"] = "dialogue_drama"
    spec["dialogue_spoken_lang"] = spec.get("dialogue_spoken_lang") or "zh"
    spec["narration_spoken_lang"] = spec.get("narration_spoken_lang") or "zh"
    spec["caption_lang"] = spec.get("caption_lang") or "zh"
    spec["compatibility"] = {
        "vo_mode": reason,
        "source_projection_mutated": False,
    }
    return spec


def _compatibility_director_intent(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    """Project only signed director intent into legacy compiled specs."""
    if isinstance(spec.get("director_intent"), dict):
        return spec
    contract_path = root / "director-contract.json"
    if not contract_path.is_file():
        return spec
    contract = read_json(contract_path)
    if str(contract.get("status") or "").lower() != "locked":
        return spec
    intent = contract.get("intent")
    if not isinstance(intent, dict):
        return spec
    required = ("logline", "tone", "emotional_arc")
    if not all(intent.get(key) for key in required):
        return spec
    spec = dict(spec)
    spec["director_intent"] = {
        key: intent[key]
        for key in ("logline", "tone", "emotional_arc", "audience")
        if key in intent
    }
    spec.setdefault("compatibility", {})["director_intent"] = (
        "projected_from_locked_director_contract"
    )
    return spec


def _compatibility_screen_modes(spec: dict[str, Any]) -> dict[str, Any]:
    """Only label explicitly silent legacy shots; leave ambiguous shots blocked."""
    changed = False
    spec = dict(spec)
    scenes = []
    for scene in spec.get("scenes") or []:
        scene_copy = dict(scene) if isinstance(scene, dict) else scene
        if isinstance(scene_copy, dict):
            shots = []
            for shot in scene_copy.get("shots") or []:
                shot_copy = dict(shot) if isinstance(shot, dict) else shot
                if (
                    isinstance(shot_copy, dict)
                    and not shot_copy.get("screen_mode")
                    and shot_copy.get("silent") is True
                ):
                    shot_copy["screen_mode"] = "silence"
                    changed = True
                shots.append(shot_copy)
            scene_copy["shots"] = shots
        scenes.append(scene_copy)
    if changed:
        spec["scenes"] = scenes
        spec.setdefault("compatibility", {})["screen_mode"] = "silence_from_explicit_silent_shots"
    return spec


def _compatibility_audio_cues(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    """Project declared locked-shot sound intent into non-executed cue plans."""
    contract_path = root / "director-contract.json"
    if not contract_path.is_file():
        return spec
    contract = read_json(contract_path)
    if str(contract.get("status") or "").lower() != "locked":
        return spec
    sounds = {
        str(shot.get("id")): shot.get("sound")
        for scene in contract.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict) and isinstance(shot.get("sound"), dict)
    }
    changed = False
    spec = dict(spec)
    scenes = []
    for scene in spec.get("scenes") or []:
        scene_copy = dict(scene) if isinstance(scene, dict) else scene
        if isinstance(scene_copy, dict):
            shots = []
            for shot in scene_copy.get("shots") or []:
                shot_copy = dict(shot) if isinstance(shot, dict) else shot
                sound = sounds.get(str(shot_copy.get("id") if isinstance(shot_copy, dict) else ""))
                if (
                    isinstance(shot_copy, dict)
                    and shot_copy.get("silent") is True
                    and not shot_copy.get("audio_cues")
                    and isinstance(sound, dict)
                ):
                    duration = float(
                        shot_copy.get("duration_seconds") or shot_copy.get("duration_sec") or 0
                    )
                    ambience = str(sound.get("ambience") or "declared scene ambience")
                    cues = [
                        {
                            "kind": "ambience",
                            "start_offset_sec": 0,
                            "duration_sec": duration,
                            "asset_hint": ambience,
                        }
                    ]
                    for effect in (sound.get("effects") or [])[:2]:
                        cues.append(
                            {
                                "kind": "sfx",
                                "start_offset_sec": min(duration - 0.25, 1.0 + len(cues)),
                                "duration_sec": 0.25,
                                "asset_hint": str(effect),
                            }
                        )
                    shot_copy["audio_cues"] = cues
                    changed = True
                shots.append(shot_copy)
            scene_copy["shots"] = shots
        scenes.append(scene_copy)
    if changed:
        spec["scenes"] = scenes
        spec.setdefault("compatibility", {})["audio_cues"] = (
            "projected_from_locked_contract_sound_intent"
        )
    return spec


def _compatibility_dramatic_functions(spec: dict[str, Any]) -> dict[str, Any]:
    """Map only explicit legacy shot evidence into the current role enum."""
    spec = dict(spec)
    changed = False
    scenes = []
    for scene in spec.get("scenes") or []:
        current = dict(scene) if isinstance(scene, dict) else scene
        if isinstance(current, dict):
            shots = []
            for shot in current.get("shots") or []:
                item = dict(shot) if isinstance(shot, dict) else shot
                if isinstance(item, dict) and not item.get("dramatic_function"):
                    if str(item.get("screen_mode") or "") == "reaction":
                        item["dramatic_function"] = "reaction"
                    elif str(item.get("screen_mode") or "") == "silence" or item.get(
                        "director_beat"
                    ):
                        item["dramatic_function"] = "action"
                    else:
                        shots.append(item)
                        continue
                    changed = True
                shots.append(item)
            current["shots"] = shots
        scenes.append(current)
    if changed:
        spec["scenes"] = scenes
        spec.setdefault("compatibility", {})["dramatic_function"] = (
            "mapped_from_locked_shot_evidence"
        )
    return spec


def cmd_write_spec(args: argparse.Namespace) -> int:
    from core.constants import DEFAULT_FPS, DEFAULT_HEIGHT, DEFAULT_WIDTH
    from core.film_io import ensure_tree, load_manifest, save_manifest
    from core.gates import recompute_gates

    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    try:
        from narrative_control import NarrativeControlError, assert_projection_ready

        # write-spec creates the projection that later media gates require locked.
        assert_projection_ready(root, require_locked=False)
    except NarrativeControlError as exc:
        raise FilmError(f"{exc.code}: {exc}") from exc
    default_spec = root / "film-spec.json"
    spec_path = Path(args.spec).expanduser().resolve() if args.spec else default_spec
    spec = _compatibility_dramatic_functions(
        _compatibility_audio_cues(
            _compatibility_director_intent(
                _compatibility_screen_modes(_compatibility_vo_mode(read_json(spec_path))), root
            ),
            root,
        )
    )
    try:
        shots = validate_film_spec(
            spec,
            assign_missing_ids=True,
            film_root=root,
            enforce_narrative_timeline=True,
        )
    except FilmSpecError as exc:
        raise FilmError(str(exc)) from exc

    from cinematic_audit import audit

    # Write-spec is the graph-projection boundary and never admits an
    # incoherent shot contract into production.
    cinematic = audit(root, spec=spec)
    if not cinematic.get("ok"):
        raise FilmError(
            "cinematic audit failed: " + ",".join(cinematic.get("blocking_codes") or [])
        )

    from drama_graph import derive_graph

    # Validate the complete contract against a disposable projection before
    # touching the project. A rejected legacy spec must not become the new
    # on-disk truth merely because its graph has not yet been refreshed.
    with tempfile.TemporaryDirectory(prefix="aifilm-cinematic-") as staging:
        stage_root = Path(staging)
        write_json(stage_root / "film-spec.json", spec)
        staged_graph = derive_graph(stage_root, write=False)
        strict_cinematic = audit(
            root,
            spec=spec,
            graph=staged_graph,
            require_authored_contract=True,
        )
    if not strict_cinematic.get("ok"):
        raise FilmError(
            "cinematic audit failed: " + ",".join(strict_cinematic.get("blocking_codes") or [])
        )

    # --- New Visual Bible Prompt Injector Logic ---
    bible = load_bible(root)
    injector = PromptInjector(bible)
    conflict_errors = []
    for shot in shots:
        try:
            injector.assemble(shot, root)
        except PromptConflictError as e:
            conflict_errors.append(str(e))

    if conflict_errors:
        err_msg = "Prompt conflicts detected:\n- " + "\n- ".join(conflict_errors)
        raise FilmError(err_msg)

    # Wardrobe State Linting (shot-level continuity write-back preferred).
    # Only hard-fail when the bible has actually authored wardrobe_variants —
    # empty bible (fresh init) must not block write-spec on adult scaffolds that
    # already declare wardrobe_state for heat ladder continuity.
    wardrobe_variants = bible.get("wardrobe_variants", {})
    wardrobe_errors = []
    if isinstance(wardrobe_variants, dict) and wardrobe_variants:
        for shot in shots:
            w_state = shot.get("wardrobe_state") or (shot.get("dsl") or {}).get("wardrobe_state")
            if w_state and w_state != "default":
                heroines = shot.get("heroine_ids", ["hero"])
                # also honor dsl.cast when heroine_ids default
                cast = (shot.get("dsl") or {}).get("cast")
                if isinstance(cast, list) and cast and heroines == ["hero"]:
                    heroines = [str(c) for c in cast if c]
                for h in heroines:
                    variants = wardrobe_variants.get(h) or wardrobe_variants.get("hero") or {}
                    if w_state not in variants:
                        wardrobe_errors.append(
                            f"Shot {shot.get('id', '?')} requests wardrobe '{w_state}' for '{h}', "
                            f"but it is not defined in the Visual Bible."
                        )

    if wardrobe_errors:
        err_msg = "Wardrobe Linting Failed:\n- " + "\n- ".join(wardrobe_errors)
        raise FilmError(err_msg)
    # ---------------------------------------------

    # Long-form: ensure continuity_chain.md skeleton exists (never overwrite without force)
    chain_path = None
    if is_long_form(spec, shots):
        chain_path = init_chain_doc(root, spec, force=False)
        spec["_continuity_chain"] = {
            "long_form": True,
            "doc": str(chain_path),
            "required": True,
            "note": (
                "Long-form: maintain continuity_chain.md; continue joins byte-reuse last frame "
                "as next keyframe (extract-frame --promote-keyframe). "
                "See references/continuity_chain.md"
            ),
        }
    else:
        spec["_continuity_chain"] = {
            "long_form": False,
            "required": False,
            "note": "Short form: continue joins still should promote last frame; doc optional",
        }
    write_json(root / "film-spec.json", spec)
    # The film spec is the projection source at this boundary. Rebuild its
    # graph before producing a strict audit so no production command can see a
    # stale or pre-contract beat map.
    derive_graph(root, write=True)
    manifest = load_manifest(root)
    # seed timeline placeholders
    timeline = {
        "schema_version": 1,
        "fps": DEFAULT_FPS,
        "width": manifest.get("width", DEFAULT_WIDTH),
        "height": manifest.get("height", DEFAULT_HEIGHT),
        "shots": [
            {
                "id": shot["id"],
                "duration_sec": float(shot.get("duration_sec") or 5.2),
                "title": shot.get("title") or shot["id"],
            }
            for shot in shots
        ],
    }
    write_json(root / "timeline.json", timeline)
    truth = manifest.setdefault(
        "truth_contract",
        {"source_of_truth": "local-contract-and-receipts"},
    )
    truth["contract_sha256"] = sha256_file(root / "film-spec.json")
    truth["spec_sha256"] = truth["contract_sha256"]
    graph_path = root / "drama-graph.json"
    truth["graph_sha256"] = sha256_file(graph_path) if graph_path.is_file() else ""
    truth["timeline_sha256"] = sha256_file(root / "timeline.json")
    longform_plan = None
    if spec.get("production_mode") == "longform":
        try:
            from longform import LongformError, build_longform_plan

            longform_plan = build_longform_plan(root, write=True)
        except LongformError as exc:
            raise FilmError(f"longform production plan failed: {exc}") from exc
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    cont = spec.get("_continuity_lint") or lint_continuity(shots)
    write_json(root / "continuity_lint.json", cont)
    # Reconcile after writing the projection so the receipt binds the current
    # shot actions instead of the stale pre-write spec.
    try:
        from scene_sound import reconcile as reconcile_scene_sound

        scene_sound = reconcile_scene_sound(root, write=True)
    except Exception as exc:
        raise FilmError(f"scene-sound reconcile failed: {exc}") from exc
    from cinematic_audit import write_audit

    cinematic_receipt = write_audit(root, require_authored_contract=True)
    if not cinematic_receipt.get("ok"):
        raise FilmError(
            "cinematic audit failed after projection: "
            + ",".join(cinematic_receipt.get("blocking_codes") or [])
        )

    # S0.2 · plan-time duration honesty (fail-closed hard codes; receipt always)
    duration_target_rep: dict[str, Any] | None = None
    try:
        from plan.duration_target import (
            check_duration_target,
            write_duration_target_receipt,
        )

        duration_target_rep = check_duration_target(spec)
        write_duration_target_receipt(root, duration_target_rep)
        try:
            from core.skip_audit import skip_flag

            skip_dt = skip_flag(
                "AIFILM_SKIP_DURATION_TARGET",
                origin="env",
                film_root=root,
                call_site="write_spec.duration_target",
            )
        except Exception:
            skip_dt = os.environ.get("AIFILM_SKIP_DURATION_TARGET", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if (
            not skip_dt
            and duration_target_rep.get("severity") == "hard"
            and not duration_target_rep.get("ok")
        ):
            raise FilmError(
                "duration target honesty failed at write-spec: "
                + str(duration_target_rep.get("message") or duration_target_rep.get("codes"))
                + " — next: "
                + "; ".join(str(x) for x in (duration_target_rep.get("next") or [])[:3])
                + " (escape AIFILM_SKIP_DURATION_TARGET=1)"
            )
    except FilmError:
        raise
    except Exception as exc:  # noqa: BLE001 — never block write-spec on probe crash
        duration_target_rep = {"ok": False, "error": str(exc)[:200]}

    _emit(
        {
            "ok": True,
            "root": str(root),
            "shot_count": len(shots),
            "timeline": str(root / "timeline.json"),
            "continuity": cont,
            "framing_lint": spec.get("_framing_lint"),
            "continuity_chain_doc": str(chain_path) if chain_path else None,
            "long_form": is_long_form(spec, shots),
            "longform_plan": {
                "path": str(root / "receipts" / "longform-production-plan.json"),
                "unit_count": len(longform_plan.get("units") or []),
                "content_sha256": longform_plan.get("content_sha256"),
            }
            if isinstance(longform_plan, dict)
            else None,
            "transition_intents": spec.get("transition_intents"),
            "sound_plan": spec.get("sound_plan"),
            "scene_sound": scene_sound,
            "cinematic_audit": cinematic_receipt,
            "duration_target": duration_target_rep,
        }
    )
    return 0

