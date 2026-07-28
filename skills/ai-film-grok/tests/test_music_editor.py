from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from music_editor import (  # noqa: E402
    build_music_edit_plan,
    edit_variant_recipes,
    harmonic_compatibility,
    motif_development_recipes,
    normalize_keyscale,
    plan_transition,
    transition_bridge_recipe,
)


def test_key_normalization_and_camelot_relationships() -> None:
    assert normalize_keyscale("A minor") == {
        "label": "A minor",
        "pitch_class": 9,
        "mode": "minor",
        "camelot": "8A",
    }
    relative = harmonic_compatibility("A minor", "C Major")
    adjacent = harmonic_compatibility("A minor", "E minor")
    distant = harmonic_compatibility("A minor", "F# Major")

    assert relative["compatible"] is True
    assert relative["relation"] == "relative"
    assert adjacent["compatible"] is True
    assert adjacent["relation"] == "adjacent"
    assert distant["compatible"] is False
    assert distant["score"] == 0.0


def test_transition_plan_uses_beats_or_requests_a_repaint_bridge() -> None:
    compatible = plan_transition(
        {
            "asset_id": "a",
            "bpm": 72,
            "keyscale": "A minor",
            "timesignature": "4/4",
        },
        {
            "asset_id": "b",
            "bpm": 74,
            "keyscale": "C Major",
            "timesignature": "4/4",
            "transition": "crossfade",
        },
    )
    incompatible = plan_transition(
        {
            "asset_id": "a",
            "bpm": 72,
            "keyscale": "A minor",
            "timesignature": "4/4",
        },
        {
            "asset_id": "c",
            "bpm": 110,
            "keyscale": "F# Major",
            "timesignature": "4/4",
            "transition": "crossfade",
        },
    )

    assert compatible["mode"] == "beat_crossfade"
    assert compatible["align"] == "bar"
    assert compatible["generation_required"] is False
    assert 4.0 <= compatible["duration_sec"] <= 8.0
    assert incompatible["mode"] == "repaint_bridge"
    assert incompatible["generation_required"] is True
    assert incompatible["reason"] == "harmonic_and_tempo_mismatch"


def test_edit_plan_never_silently_raw_truncates_a_master() -> None:
    receipt = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "film-a",
        "catalog_revision": 7,
        "catalog_sha256": "a" * 64,
        "selections": [
            {
                "shot_id": "s1",
                "start_sec": 0.0,
                "end_sec": 12.0,
                "asset_id": "warm-master",
                "path": "/library/warm.wav",
                "sha256": "b" * 64,
                "duration_sec": 60.0,
                "bpm": 72,
                "keyscale": "A minor",
                "timesignature": "4/4",
                "transition": "crossfade",
                "duck_db": -6.0,
            },
            {
                "shot_id": "s2",
                "start_sec": 12.0,
                "end_sec": 82.0,
                "asset_id": "dark-master",
                "path": "/library/dark.wav",
                "sha256": "c" * 64,
                "duration_sec": 60.0,
                "bpm": 86,
                "keyscale": "E minor",
                "timesignature": "4/4",
                "transition": "crossfade",
                "duck_db": 0.0,
            },
        ],
    }

    plan = build_music_edit_plan(receipt)

    assert plan["schema"] == "aifilm-music-edit-plan-v1"
    assert plan["edits"][0]["strategy"] == "cover_cutdown"
    assert plan["edits"][0]["dialogue_safe_required"] is True
    assert plan["edits"][0]["raw_truncation_allowed"] is False
    assert plan["edits"][1]["strategy"] == "loop_then_repaint_outro"
    assert plan["edits"][1]["raw_truncation_allowed"] is False
    assert plan["transitions"][1]["mode"] == "tempo_bridge"
    assert plan["ready_for_final"] is False
    assert {item["kind"] for item in plan["requirements"]} == {
        "approved_edit_variant",
        "approved_transition_bridge",
    }


def test_edit_plan_is_ready_when_exact_dialogue_safe_assets_are_approved() -> None:
    receipt = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "film-ready",
        "catalog_revision": 3,
        "catalog_sha256": "a" * 64,
        "selections": [
            {
                "shot_id": "s1",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "asset_id": "approved-exact",
                "path": "/library/exact.wav",
                "sha256": "b" * 64,
                "duration_sec": 20.0,
                "bpm": 72,
                "keyscale": "A minor",
                "timesignature": "4/4",
                "transition": "cut",
                "duck_db": -6.0,
                "dialogue_safe": True,
            }
        ],
    }

    plan = build_music_edit_plan(receipt)

    assert plan["ready_for_final"] is True
    assert plan["requirements"] == []


def test_edit_plan_does_not_treat_subsecond_mismatch_as_exact() -> None:
    receipt = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "film-near-mismatch",
        "catalog_revision": 3,
        "catalog_sha256": "a" * 64,
        "selections": [
            {
                "shot_id": "s1",
                "start_sec": 0.0,
                "end_sec": 10.0,
                "asset_id": "near-master",
                "path": "/library/near.wav",
                "sha256": "b" * 64,
                "duration_sec": 10.24,
                "bpm": 72,
                "keyscale": "A minor",
                "timesignature": "4/4",
                "transition": "cut",
            }
        ],
    }

    plan = build_music_edit_plan(receipt)

    assert plan["ready_for_final"] is False
    assert plan["edits"][0]["strategy"] == "repaint_outro"


def test_edit_variant_recipes_are_offline_pending_asset_requests() -> None:
    parent = {
        "asset_id": "warm-1",
        "mood": "warm",
        "dramatic_tags": ["character", "identity"],
        "bpm": 72,
        "keyscale": "A minor",
        "timesignature": "4/4",
        "motif_family": "protagonist",
        "series_id": "series-a",
    }
    recipes = edit_variant_recipes(
        parent,
        parent_path=Path("/library/approved/warm-1.wav"),
        target_duration=20.0,
        variants=("exact", "dialogue-safe", "loop", "outro"),
    )

    assert {item["edit_variant"] for item in recipes} == {
        "exact",
        "dialogue-safe",
        "loop",
        "outro",
    }
    assert all(item["parent_asset_id"] == "warm-1" for item in recipes)
    assert all(item["reference_audio"].endswith("warm-1.wav") for item in recipes)
    assert all(item["duration"] == 20.0 for item in recipes)
    assert (
        next(item for item in recipes if item["edit_variant"] == "outro")["task_type"] == "repaint"
    )
    assert (
        next(item for item in recipes if item["edit_variant"] == "dialogue-safe")["dialogue_safe"]
        is True
    )
    assert next(item for item in recipes if item["edit_variant"] == "loop")["loopable"] is True


def test_motif_development_covers_the_full_story_arc() -> None:
    parent = {
        "asset_id": "relationship-master",
        "mood": "rnb",
        "dramatic_tags": ["relationship", "intimacy"],
        "bpm": 72,
        "keyscale": "A minor",
        "timesignature": "4/4",
        "motif_family": "relationship",
        "series_id": "series-a",
    }
    recipes = motif_development_recipes(
        parent,
        parent_path=Path("/library/approved/relationship.wav"),
    )

    assert {item["motif_role"] for item in recipes} == {
        "statement",
        "fragment",
        "tender",
        "corrupted",
        "reveal",
        "loss",
        "reunion",
        "climax",
    }
    assert all(item["task_type"] == "cover" for item in recipes)
    assert all(item["series_id"] == "series-a" for item in recipes)


def test_transition_bridge_recipe_binds_both_approved_assets() -> None:
    outgoing = {
        "asset_id": "outgoing",
        "mood": "warm",
        "bpm": 72,
        "keyscale": "A minor",
        "timesignature": "4/4",
    }
    incoming = {
        "asset_id": "incoming",
        "mood": "dark",
        "bpm": 110,
        "keyscale": "F# Major",
        "timesignature": "4/4",
    }

    recipe = transition_bridge_recipe(
        outgoing,
        incoming,
        outgoing_path=Path("/library/outgoing.wav"),
        duration=10,
    )

    assert recipe["edit_variant"] == "bridge"
    assert recipe["parent_asset_id"] == "outgoing"
    assert recipe["transition_to_asset_id"] == "incoming"
    assert recipe["keyscale"] == "F# Major"
    assert recipe["bpm"] == 110
    assert recipe["approval_required"] is True
