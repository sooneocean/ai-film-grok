"""Receipt-backed audio weapons for the private ACE-Step node.

This deliberately lives beside, not inside, the visual Comfy armory: music
generation is offline curation and every result requires human approval.
"""

from __future__ import annotations

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
