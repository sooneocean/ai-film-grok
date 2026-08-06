from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from scripts.department_contracts import (
    migrate_asset_registry,
    migrate_audio_bible,
    migrate_post_bible,
)

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _assert_node(node: dict, expected_id: str) -> None:
    assert node["id"] == expected_id
    assert node["revision"] >= 1
    assert len(node["hash"]) == 64
    assert node["source_refs"]
    assert isinstance(node["dependency_refs"], list)
    assert node["state"] in {"draft", "review", "locked", "stale"}
    assert "approval_ref" in node
    assert isinstance(node["stale_reasons"], list)
    assert "data" in node


def test_audio_bible_migrates_free_text_without_losing_it() -> None:
    migrated = migrate_audio_bible("warm intimate sound with a recurring piano theme")

    assert migrated["schema_version"] == 1
    assert migrated["legacy_payload"] == "warm intimate sound with a recurring piano theme"
    assert set(migrated["nodes"]) == {
        "voice",
        "dialogue_delivery",
        "adr_lipsync",
        "ambience",
        "foley",
        "sfx",
        "bgm_motif_cue",
        "licensing",
    }
    for key, node in migrated["nodes"].items():
        _assert_node(node, f"audio.{key}.primary")
    jsonschema.validate(migrated, _schema("audio-bible.schema.json"))


def test_post_bible_preserves_media_and_downgrades_historic_approval() -> None:
    legacy = {
        "state": "Approved",
        "locked": True,
        "edl": {"path": "edit/final.edl"},
        "media": [{"path": "out/rough.mp4", "sha256": "a" * 64}],
    }

    migrated = migrate_post_bible(legacy)

    assert migrated["edl"] == legacy["edl"]
    assert migrated["media"] == legacy["media"]
    assert migrated["state"] == "review"
    assert migrated["locked"] is True
    assert any(
        reason["code"] == "LEGACY_APPROVAL_UNVERIFIED" for reason in migrated["stale_reasons"]
    )
    assert migrated["nodes"]["edl"]["data"]["edl"] == legacy["edl"]
    assert set(migrated["nodes"]) == {
        "coverage",
        "takes",
        "edl",
        "picture_lock",
        "vfx",
        "color",
        "captions",
        "mix",
        "master",
    }
    jsonschema.validate(migrated, _schema("post-bible.schema.json"))


def test_node_ids_and_hashes_are_stable_across_repeat_migration() -> None:
    legacy = {"voice": {"hero": "eve"}, "dialogue": "restrained", "revision": 4}
    first = migrate_audio_bible(legacy)
    second = migrate_audio_bible(first)

    assert first["nodes"] == second["nodes"]
    assert first["revision"] == second["revision"] == 4


def test_valid_new_approval_can_preserve_locked_state() -> None:
    raw = {
        "state": "locked",
        "approval_ref": "approval-current",
        "voice": "eve",
    }
    migrated = migrate_audio_bible(raw, valid_approval_refs={"approval-current"})
    assert migrated["state"] == "locked"
    assert migrated["approval_ref"] == "approval-current"


def test_asset_registry_runtime_migration_tightens_legacy_items() -> None:
    legacy = {
        "schema_version": 1,
        "kind": "asset-registry",
        "characters": ["hero"],
        "locations": {"room": "a blue room"},
        "props": ["cup"],
        "characterStatesTimeline": [
            {"shotId": "shot-1", "characterId": "hero", "wardrobeState": "full"}
        ],
        "media": [{"path": "canonical/hero.png"}],
    }
    migrated = migrate_asset_registry(legacy)

    assert migrated["schema_version"] == 2
    assert migrated["characters"][0]["id"] == "hero"
    assert migrated["locations"][0]["id"] == "room"
    assert migrated["props"][0]["id"] == "cup"
    assert migrated["media"] == legacy["media"]
    assert migrated["characterStatesTimeline"][0]["characterRef"] == "asset.character.hero"
    jsonschema.validate(migrated, _schema("assets-registry.schema.json"))
