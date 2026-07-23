"""Tests for P1-5/P1-6: scene design sheet + art direction.

Verifies:
- drama_graph Location schema expanded with art direction fields
- derive_graph fills locationId (was hardcoded None)
- SCENE_LOCATION_MISSING lint fires on shots without locationId
- style-bible art_direction layer (color_script/visual_motifs/texture_continuity)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from continuity import CODE_SCENE_LOCATION_MISSING, lint_continuity


class TestSceneLocationMissing:
    """SCENE_LOCATION_MISSING lint fires when shot has no locationId."""

    def test_shot_without_location_triggers_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"cast": ["hero"]}},
            {"id": "s2", "dramatic_function": "action", "dsl": {"cast": ["hero"]}},
        ]
        result = lint_continuity(shots)
        codes = result.get("codes", [])
        assert CODE_SCENE_LOCATION_MISSING in codes

    def test_shot_with_locationId_no_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"cast": ["hero"]}, "locationId": "loc1"},
            {"id": "s2", "dramatic_function": "action", "dsl": {"cast": ["hero"]}, "locationId": "loc1"},
        ]
        result = lint_continuity(shots)
        codes = result.get("codes", [])
        assert CODE_SCENE_LOCATION_MISSING not in codes

    def test_shot_with_dsl_location_no_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"cast": ["hero"], "location": "taxi"}},
        ]
        result = lint_continuity(shots)
        codes = result.get("codes", [])
        assert CODE_SCENE_LOCATION_MISSING not in codes

    def test_location_missing_is_warning_not_error(self):
        shots = [{"id": "s1", "dramatic_function": "hook"}]
        result = lint_continuity(shots)
        for iss in result.get("issues", []):
            if iss["code"] == CODE_SCENE_LOCATION_MISSING:
                assert iss["severity"] == "warning"


class TestDeriveGraphLocationId:
    """derive_graph fills locationId (was hardcoded None)."""

    def test_derive_graph_fills_scene_locationId(self):
        from drama_graph import derive_graph

        spec = {
            "title": "Test",
            "scenes": [
                {
                    "title": "Scene 1",
                    "locationId": "loc_rainy_street",
                    "shots": [
                        {
                            "id": "s1",
                            "nar": "test nar",
                            "dramatic_function": "hook",
                            "dsl": {"motion": "dolly_in", "action": "walking"},
                        }
                    ],
                }
            ],
        }
        graph = derive_graph(spec)
        scenes = graph.get("episodes", [{}])[0].get("scenes", [])
        assert len(scenes) >= 1
        assert scenes[0].get("locationId") == "loc_rainy_street"

    def test_derive_graph_fills_shot_locationId_from_scene(self):
        from drama_graph import derive_graph

        spec = {
            "title": "Test",
            "scenes": [
                {
                    "title": "Scene 1",
                    "locationId": "loc_bar",
                    "shots": [
                        {
                            "id": "s1",
                            "nar": "test",
                            "dramatic_function": "hook",
                            "dsl": {"motion": "dolly_in", "action": "standing"},
                        }
                    ],
                }
            ],
        }
        graph = derive_graph(spec)
        shots = []
        for ep in graph.get("episodes", []):
            for sc in ep.get("scenes", []):
                for bt in sc.get("beats", []):
                    shots.extend(bt.get("shots", []))
        assert len(shots) >= 1
        assert shots[0].get("locationId") == "loc_bar"

    def test_derive_graph_infers_location_from_dsl(self):
        """When scene has no locationId, infer from shot dsl.location."""
        from drama_graph import derive_graph

        spec = {
            "title": "Test",
            "scenes": [
                {
                    "title": "Scene 1",
                    "shots": [
                        {
                            "id": "s1",
                            "nar": "test",
                            "dramatic_function": "hook",
                            "dsl": {"motion": "dolly_in", "action": "standing", "location": "taxi_interior"},
                        }
                    ],
                }
            ],
        }
        graph = derive_graph(spec)
        scenes = graph.get("episodes", [{}])[0].get("scenes", [])
        assert scenes[0].get("locationId") == "taxi_interior"


class TestArtDirectionSchema:
    """style-bible art_direction layer exists in schema."""

    def test_art_direction_field_exists(self):
        import json

        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "style-bible.schema.json"
        schema = json.loads(schema_path.read_text())
        props = schema.get("properties", {})
        assert "art_direction" in props
        ad = props["art_direction"]
        assert ad["type"] == "object"
        ad_props = ad.get("properties", {})
        assert "color_script" in ad_props
        assert "visual_motifs" in ad_props
        assert "texture_continuity" in ad_props

    def test_location_schema_has_art_direction_fields(self):
        import json

        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "drama-graph.schema.json"
        schema = json.loads(schema_path.read_text())
        loc = schema.get("$defs", {}).get("Location", {})
        props = loc.get("properties", {})
        assert "color_temperature" in props
        assert "set_dressing" in props
        assert "lighting_plot" in props
        assert "atmosphere" in props
