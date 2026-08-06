from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from scripts.visual_bible import migrate_to_v3

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "style-bible.schema.json").read_text(
        encoding="utf-8"
    )
)


def test_style_v1_migration_preserves_all_legacy_fields_and_media() -> None:
    legacy = {
        "title": "Legacy",
        "identity_lock": "silver hair, red eyes",
        "medium": "anime",
        "palette": "blue and amber",
        "lens": "50mm",
        "locations": {"room": "small apartment"},
        "props": {"cup": "chipped cup"},
        "cast_masters": {"hero": "canonical/hero.png"},
        "media": [{"path": "refs/look.jpg", "role": "look-reference"}],
        "locked": True,
    }

    migrated = migrate_to_v3(legacy)

    for key, value in legacy.items():
        assert migrated[key] == value
    assert migrated["schema_version"] == 3
    assert migrated["state"] == "review"
    assert migrated["nodes"]["face"]["data"]["identity_lock"] == legacy["identity_lock"]
    assert migrated["nodes"]["location"]["data"]["locations"] == legacy["locations"]
    assert migrated["nodes"]["prop"]["data"]["props"] == legacy["props"]
    assert set(migrated["nodes"]) == {
        "face",
        "geometry",
        "body",
        "hair",
        "makeup",
        "wardrobe",
        "art",
        "location",
        "prop",
        "cinematography",
    }
    for key, node in migrated["nodes"].items():
        assert node["id"] == f"visual.{key}.primary"
        assert len(node["hash"]) == 64
        assert node["state"] in {"draft", "review", "locked", "stale"}
    jsonschema.validate(migrated, SCHEMA)


def test_style_v2_migration_is_idempotent_and_keeps_unknown_fields() -> None:
    legacy = {
        "schema_version": 2,
        "state": "Candidate",
        "characters": {"hero": {"identity": "same person"}},
        "wardrobe_variants": {"hero": {"full": "red coat"}},
        "custom_vendor_media": {"contact_sheet": "refs/sheet.png"},
    }
    first = migrate_to_v3(legacy)
    second = migrate_to_v3(first)

    assert first == second
    assert first["custom_vendor_media"] == legacy["custom_vendor_media"]
    assert first["nodes"]["wardrobe"]["data"]["wardrobe_variants"] == legacy["wardrobe_variants"]
