"""Receipt-backed audio weapons for the private ACE-Step node.

This deliberately lives beside, not inside, the visual Comfy armory: music
generation is offline curation and every result requires human approval.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from bgm_library import _load_catalog

_WEAPONS = (
    ("ace_score_master", "score_master", "Approved shared instrumental masters"),
    ("ace_scene_editor", "scene_edit", "Dialogue-safe and repaired-outro cover edits"),
    ("ace_transition_bridge", "transition_bridge", "Exact-duration harmonic/tempo handoffs"),
    ("ace_motif_developer", "motif_development", "Series motif dramatic variations"),
    ("ace_trailer_bumper", "trailer_bumper", "10-60 second musical hooks and stingers"),
)

_INTENTS = {intent for _, intent, _ in _WEAPONS}


def plan_audio_weapon(
    library_root: Path | str,
    *,
    node: dict[str, Any] | None,
    intent: str,
    asset_id: str = "",
    to_asset_id: str = "",
    film_root: str = "",
    series_id: str = "",
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """Return a no-side-effect ACE curation route for one evidenced intent.

    The command templates deliberately remain templates: this planner never talks
    to the node, writes a receipt, generates a candidate, or approves audio.
    """
    if intent not in _INTENTS:
        raise ValueError(f"unsupported ACE audio intent: {intent}")
    if duration_sec is not None and (
        not math.isfinite(float(duration_sec)) or not 10.0 <= float(duration_sec) <= 600.0
    ):
        raise ValueError("ACE audio plan duration must be between 10 and 600 seconds")
    armory = inspect_audio_armory(library_root, node=node)
    weapon = next(item for item in armory["weapons"] if item["intent"] == intent)
    catalog = _load_catalog(Path(library_root).expanduser().resolve())
    assets = catalog.get("assets", {})

    def approved(identifier: str) -> bool:
        return (
            bool(identifier)
            and isinstance(assets.get(identifier), dict)
            and (assets[identifier].get("status") == "approved")
        )

    def approved_series_motif(identifier: str) -> bool:
        record = assets.get(identifier)
        if not isinstance(record, dict) or not approved(identifier):
            return False
        if str(record.get("series_id") or "") != series_id or not record.get("motif_family"):
            return False
        recipe = record.get("recipe")
        recipe_id = str(recipe.get("recipe_id") or "") if isinstance(recipe, dict) else ""
        return recipe_id.startswith(f"series-{series_id}-{record['motif_family']}-")

    prerequisites: list[dict[str, Any]] = []
    commands: list[list[str]] = []
    required: list[tuple[str, bool, str]] = []
    if intent == "score_master":
        commands.append(
            [
                "aifilm",
                "bgm-library",
                "generate",
                "--recipe-pack",
                "baseline-v1",
                "--batch-size",
                "4",
            ]
        )
    elif intent == "scene_edit":
        required.append(
            ("approved_asset_id", approved(asset_id), "provide --asset-id for an approved master")
        )
        chosen_duration = duration_sec or 20.0
        if approved(asset_id):
            commands.append(
                [
                    "aifilm",
                    "bgm-library",
                    "edit-pack",
                    "--asset-id",
                    asset_id,
                    "--duration",
                    f"{chosen_duration:g}",
                    "--variant",
                    "dialogue-safe",
                ]
            )
    elif intent == "transition_bridge":
        required.extend(
            [
                ("approved_from_asset_id", approved(asset_id), "provide an approved --asset-id"),
                (
                    "approved_to_asset_id",
                    approved(to_asset_id),
                    "provide an approved --to-asset-id",
                ),
            ]
        )
        chosen_duration = duration_sec or 10.0
        if approved(asset_id) and approved(to_asset_id):
            commands.append(
                [
                    "aifilm",
                    "bgm-library",
                    "bridge-pack",
                    "--from-asset-id",
                    asset_id,
                    "--to-asset-id",
                    to_asset_id,
                    "--duration",
                    f"{chosen_duration:g}",
                ]
            )
    elif intent == "motif_development":
        has_series_motif = approved_series_motif(asset_id)
        required.extend(
            [
                ("film_root", bool(film_root), "provide --root for the series receipt"),
                ("series_id", bool(series_id), "provide --series-id"),
                (
                    "approved_series_motif_asset_id",
                    has_series_motif,
                    "provide an approved same-series series-pack motif candidate as --asset-id",
                ),
            ]
        )
        if film_root and series_id and not has_series_motif:
            commands.append(
                [
                    "aifilm",
                    "bgm-library",
                    "series-pack",
                    "--root",
                    film_root,
                    "--series-id",
                    series_id,
                ]
            )
        if film_root and has_series_motif:
            commands.append(
                [
                    "aifilm",
                    "bgm-library",
                    "motif-development",
                    "--root",
                    film_root,
                    "--asset-id",
                    asset_id,
                ]
            )
    elif intent == "trailer_bumper":
        required.append(
            ("approved_asset_id", approved(asset_id), "provide --asset-id for an approved master")
        )
        chosen_duration = duration_sec or 15.0
        if approved(asset_id):
            commands.append(
                [
                    "aifilm",
                    "bgm-library",
                    "edit-pack",
                    "--asset-id",
                    asset_id,
                    "--duration",
                    f"{chosen_duration:g}",
                    "--variant",
                    "exact",
                ]
            )

    for name, satisfied, reason in required:
        prerequisites.append({"name": name, "satisfied": satisfied, "reason": reason})
    missing = [item["name"] for item in prerequisites if not item["satisfied"]]
    capability_ready = weapon["state"] == "verified"
    if not missing and intent == "motif_development" and not capability_ready:
        state = "canary_required"
    else:
        state = "ready_to_stage" if capability_ready and not missing else "blocked"
    return {
        "schema": "aifilm-audio-armory-plan-v1",
        "intent": intent,
        "state": state,
        "capability_state": weapon["state"],
        "reason": weapon["reason"],
        "generation_phase": "offline_curation",
        "auto_execute": False,
        "writes_catalog": False,
        "approval_required": True,
        "final_direct_use": False,
        "real_node_canary_required": intent == "motif_development" and not capability_ready,
        "prerequisites": prerequisites,
        "missing_prerequisites": missing,
        "candidate_command_templates": commands,
        "required_human_gate": "review-pack then approve each fully heard instrumental candidate",
        "note": (
            "motif development is two-stage: series-pack -> human approval of a motif master "
            "-> motif-development; neither stage is executed by this planner"
            if intent == "motif_development"
            else "templates create pending candidates only; final may select approved catalog assets only"
        ),
    }


def inspect_audio_armory(
    library_root: Path | str, *, node: dict[str, Any] | None
) -> dict[str, Any]:
    """Report only evidenced ACE capabilities; never authorizes generation or final use."""
    root = Path(library_root).expanduser().resolve()
    catalog = _load_catalog(root)
    assets = [item for item in catalog.get("assets", {}).values() if isinstance(item, dict)]
    healthy = bool((node or {}).get("ok")) and bool((node or {}).get("models", {}).get("music"))

    def evidenced(predicate: Any) -> bool:
        return any(
            item.get("status") in {"approved", "pending_human_review"}
            and bool((item.get("technical") or {}).get("ok"))
            and predicate(item)
            for item in assets
        )

    # Older node health payloads omit this field.  A checksum-bound successful
    # cover/repaint candidate is stronger evidence than an omitted boolean.
    reference_upload = bool((node or {}).get("music_reference_upload")) or evidenced(
        lambda item: bool(item.get("parent_asset_id"))
    )

    verified = {
        "score_master": evidenced(lambda item: not item.get("parent_asset_id")),
        "scene_edit": evidenced(
            lambda item: item.get("edit_variant") in {"dialogue-safe", "outro"}
        ),
        "transition_bridge": evidenced(lambda item: bool(item.get("transition_to_asset_id"))),
        "motif_development": evidenced(lambda item: bool(item.get("motif_role"))),
        "trailer_bumper": evidenced(
            lambda item: (
                10.0 <= float((item.get("technical") or {}).get("duration_sec") or 0) <= 60.0
            )
        ),
    }
    weapons = []
    for weapon_id, intent, description in _WEAPONS:
        state = "verified" if healthy and reference_upload and verified[intent] else "conditional"
        if intent == "motif_development" and not verified[intent]:
            reason = "needs an approved series motif master and a real-node variation canary"
        elif not healthy:
            reason = "private ACE-Step node is unavailable"
        elif not reference_upload and intent != "score_master":
            reason = "reference upload is required for cover/repaint editing"
        elif not verified[intent]:
            reason = "no checksum-bound technical-passing canary evidence"
        else:
            reason = "real-node candidate exists; remains approval-gated"
        weapons.append(
            {
                "id": weapon_id,
                "intent": intent,
                "state": state,
                "description": description,
                "generation_phase": "offline_curation",
                "approval_required": True,
                "final_direct_use": False,
                "reason": reason,
            }
        )
    return {
        "schema": "aifilm-audio-armory-v1",
        "ok": healthy,
        "node_music_ready": healthy,
        "reference_upload": reference_upload,
        "weapons": weapons,
        "excluded": [
            {
                "intent": "foley_or_frame_sync_sfx",
                "reason": "ACE-Step is not registered for frame-accurate effects; use the SFX armory instead",
            },
            {
                "intent": "seamless_loop",
                "reason": "the live loop canary failed the seam threshold; do not route it automatically",
            },
        ],
    }
