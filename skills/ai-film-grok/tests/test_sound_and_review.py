"""Tests for P3-2~P3-5: sound layering, BGM spotting, director review expansion.

Verifies:
- P3-2: audio_tracks (dialogue/SFX/ambience/foley/music) in sound_plan schema
- P3-3: music_spotting with start/end/fade/emotion in sound_plan schema
- P3-3: sound_plan events type enum includes music_in/music_out/fade_in/fade_out
- P3-5: SCORECARD_DIMENSIONS expanded to include rhythm/emotion/theme/performance
- P3-5: _DEFAULT_ACTION_FOR_DIM has new dimensions
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestSoundPlanSchema:
    """P3-2/P3-3: sound_plan schema has audio_tracks + music_spotting."""

    def test_audio_tracks_exists(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "film-spec.schema.json"
        schema = json.loads(schema_path.read_text())
        sp = schema.get("properties", {}).get("sound_plan", {})
        props = sp.get("properties", {})
        assert "audio_tracks" in props
        at = props["audio_tracks"]
        at_props = at.get("properties", {})
        assert "dialogue" in at_props
        assert "sfx" in at_props
        assert "ambience" in at_props
        assert "foley" in at_props
        assert "music" in at_props

    def test_music_spotting_exists(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "film-spec.schema.json"
        schema = json.loads(schema_path.read_text())
        sp = schema.get("properties", {}).get("sound_plan", {})
        props = sp.get("properties", {})
        assert "music_spotting" in props
        ms = props["music_spotting"]
        items = ms.get("items", {})
        ms_props = items.get("properties", {})
        assert "start_sec" in ms_props
        assert "end_sec" in ms_props
        assert "fade_in_sec" in ms_props
        assert "fade_out_sec" in ms_props
        assert "emotion" in ms_props
        assert "beat_ref" in ms_props

    def test_events_type_enum_includes_music(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "film-spec.schema.json"
        schema = json.loads(schema_path.read_text())
        sp = schema.get("properties", {}).get("sound_plan", {})
        events = sp.get("properties", {}).get("events", {})
        items = events.get("items", {})
        type_prop = items.get("properties", {}).get("type", {})
        enum_vals = type_prop.get("enum", [])
        assert "music_in" in enum_vals
        assert "music_out" in enum_vals
        assert "fade_in" in enum_vals
        assert "fade_out" in enum_vals


class TestDirectorReviewExpansion:
    """P3-5: director review scorecard expanded."""

    def test_scorecard_has_new_dimensions(self):
        from director_review import SCORECARD_DIMENSIONS

        assert "rhythm" in SCORECARD_DIMENSIONS
        assert "emotion" in SCORECARD_DIMENSIONS
        assert "theme" in SCORECARD_DIMENSIONS
        assert "performance" in SCORECARD_DIMENSIONS

    def test_scorecard_has_11_dimensions(self):
        from director_review import SCORECARD_DIMENSIONS

        assert len(SCORECARD_DIMENSIONS) == 11

    def test_default_actions_for_new_dims(self):
        from director_review import _DEFAULT_ACTION_FOR_DIM

        assert _DEFAULT_ACTION_FOR_DIM["rhythm"] == "recut"
        assert _DEFAULT_ACTION_FOR_DIM["emotion"] == "recut"
        assert _DEFAULT_ACTION_FOR_DIM["theme"] == "recut"
        assert _DEFAULT_ACTION_FOR_DIM["performance"] == "reshoot"

    def test_cli_flags_generated_for_new_dims(self):
        from director_review import SCORECARD_CLI_FLAGS

        assert "rhythm" in SCORECARD_CLI_FLAGS
        assert "emotion" in SCORECARD_CLI_FLAGS
        assert "theme" in SCORECARD_CLI_FLAGS
        assert "performance" in SCORECARD_CLI_FLAGS
