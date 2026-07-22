import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None

def write_json(path: Path, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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


def resolve_state_photo(
    bible: dict[str, Any],
    heroine_id: str,
    wardrobe_state: str,
    *,
    root: Path | None = None,
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
    csm = bible.get("cast_state_masters") if isinstance(bible.get("cast_state_masters"), dict) else {}
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
