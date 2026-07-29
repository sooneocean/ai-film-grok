from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json, write_json

try:
    from .department_contracts import migrate_style_bible
except ImportError:  # direct script imports used by the CLI
    from department_contracts import migrate_style_bible


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def migrate_to_v2(bible: dict[str, Any]) -> dict[str, Any]:
    v2_bible = bible.copy()
    already_v2 = v2_bible.get("schema_version") == 2
    if not already_v2:
        v2_bible["schema_version"] = 2
        if "state" not in v2_bible:
            v2_bible["state"] = "Approved" if v2_bible.get("locked") else "Draft"
        if "locked" not in v2_bible:
            v2_bible["locked"] = False

        # Try to extract legacy identity_lock to hero character
        identity_lock = v2_bible.get("identity_lock")
        cast_masters = v2_bible.get("cast_masters", {})
        if identity_lock and "hero" not in v2_bible.get("characters", {}):
            v2_bible.setdefault("characters", {})
            v2_bible["characters"]["hero"] = {
                "identity": identity_lock,
                "default_wardrobe": "",
                "cast_master": cast_masters.get("hero", ""),
            }

    # Initialize structured fields (also fills missing keys on already-v2 bibles)
    for field in [
        "characters",
        "wardrobe_variants",
        "wardrobe_ladders",
        "cast_state_masters",
        "locations",
        "props",
        "continuity_states",
        "approved_keyframes",
        "previous_versions",
    ]:
        if field not in v2_bible:
            if field == "previous_versions":
                v2_bible[field] = []
            else:
                v2_bible[field] = {}

    if not isinstance(v2_bible.get("cast_state_masters"), dict):
        v2_bible["cast_state_masters"] = {}

    return v2_bible


def migrate_to_v3(
    bible: dict[str, Any] | str | None,
    *,
    valid_approval_refs: set[str] | None = None,
) -> dict[str, Any]:
    """Wrap legacy visual data in independently revisioned v3 nodes."""
    return migrate_style_bible(bible, valid_approval_refs=valid_approval_refs)


def resolve_state_photo(
    bible: dict[str, Any],
    heroine_id: str,
    wardrobe_state: str,
    *,
    root: Path | None = None,
    wardrobe_state_id: str | None = None,
) -> str | None:
    """Return relative or absolute path for a character wardrobe state photo.

    Lookup order:
      cast_state_masters[hid][state]
      cast_state_masters[hero][state]  (fallback)
      canonical/wardrobe/undress-anchor.png  (if state is undressed/bare and file exists)
      cast_masters[hid]  (only when state is full/default)
    """
    state = (wardrobe_state or "full").strip().lower() or "full"
    hid = (heroine_id or "hero").strip() or "hero"
    if wardrobe_state_id:
        try:
            from wardrobe_ladder import resolve_exact_state_photo

            # An explicit ID is a fail-closed pixel contract.  Never degrade it
            # to a category match, which could select a different garment step.
            return resolve_exact_state_photo(bible, hid, wardrobe_state_id, root=root)
        except ImportError:
            pass
    try:
        from wardrobe_ladder import resolve_state_photo_for_category

        ladder_path = resolve_state_photo_for_category(bible, hid, state, root=root)
        if ladder_path:
            return ladder_path
    except ImportError:
        pass
    csm = (
        bible.get("cast_state_masters") if isinstance(bible.get("cast_state_masters"), dict) else {}
    )
    for key in (hid, "hero", "xide", "fufu", "astra"):
        block = csm.get(key)
        if isinstance(block, dict):
            p = block.get(state) or block.get("default")
            if p:
                return str(p)
    if state in {"undressed", "bare", "partial"} and root is not None:
        anchor = root / "canonical" / "wardrobe" / "undress-anchor.png"
        if anchor.is_file():
            return str(anchor)
        for alt in ("undress-anchor.jpg", "undress-anchor.webp"):
            a2 = root / "canonical" / "wardrobe" / alt
            if a2.is_file():
                return str(a2)
    if state in {"full", "armored", "default", ""}:
        cm = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
        for key in (hid, "hero"):
            if cm.get(key):
                return str(cm[key])
    return None


def load_bible(root: Path) -> dict[str, Any]:
    path = root / "style-bible.json"
    bible = read_json(path) or {"schema_version": 2, "state": "Draft", "locked": False}
    return migrate_to_v2(bible)


def save_bible(root: Path, bible: dict[str, Any]) -> None:
    path = root / "style-bible.json"
    bible["updated_at"] = utc_now()
    write_json(path, bible)


def update_bible_state(root: Path, state: str) -> None:
    bible = load_bible(root)
    valid_states = ["Draft", "Candidate", "Approved"]
    if state not in valid_states:
        raise ValueError(f"Invalid state {state}")

    # If transitioning to Approved, ensure it's locked
    if state == "Approved":
        bible["locked"] = True
    elif state == "Draft":
        bible["locked"] = False

    bible["state"] = state
    save_bible(root, bible)


LIGHTING_COLOR_PALETTES = {
    "setup": {
        "theme": "subdued_ambient",
        "description": "Natural ambient daylight/soft window light",
        "ffmpeg_filter": "eq=contrast=1.05:saturation=1.0",
    },
    "foreplay": {
        "theme": "neon_magenta_glow",
        "description": "Sensual magenta/violet neon atmosphere",
        "ffmpeg_filter": "colorbalance=rs=0.1:gs=-0.05:bs=0.15",
    },
    "act": {
        "theme": "dramatic_chiaroscuro_velvet",
        "description": "High-contrast chiaroscuro velvet shadows",
        "ffmpeg_filter": "eq=contrast=1.18:saturation=1.12",
    },
    "climax": {
        "theme": "dramatic_chiaroscuro_velvet",
        "description": "Extreme dramatic lighting, vivid highlights and deep shadows",
        "ffmpeg_filter": "eq=contrast=1.2:saturation=1.15",
    },
    "afterglow": {
        "theme": "warm_golden_hour",
        "description": "Warm golden hour warmth, soft amber glow",
        "ffmpeg_filter": "colorbalance=rs=0.15:gs=0.08:bs=-0.1",
    },
}


def derive_lighting_timeline(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive dynamic lighting and color grading timeline across shots."""
    timeline = []
    for shot in shots:
        hp = str(shot.get("heat_phase") or shot.get("heatPhase") or "setup").strip().lower()
        preset = LIGHTING_COLOR_PALETTES.get(hp) or LIGHTING_COLOR_PALETTES["setup"]
        timeline.append(
            {
                "shot_id": str(shot.get("id")),
                "heat_phase": hp,
                "lighting_theme": preset["theme"],
                "description": preset["description"],
                "ffmpeg_filter": preset["ffmpeg_filter"],
            }
        )
    return timeline
