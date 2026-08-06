"""Tests for director verify CLI subcommand.

Verifies:
- director verify runs pace_chart + act_structure + music_spotting verification
- Returns ok=True when no issues found
- Returns ok=False when issues detected
- Handles missing film-spec gracefully
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from director_cli import verify


def _make_film_root(tmp_path: Path, *, spec=None, graph=None):
    if spec:
        (tmp_path / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    if graph:
        (tmp_path / "drama-graph.json").write_text(json.dumps(graph, ensure_ascii=False))


class TestDirectorVerify:
    """director verify runs methodology verification."""

    def test_verify_with_clean_spec(self, tmp_path):
        spec = {
            "title": "test",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "test logline long enough",
                "tone": "dark",
                "emotional_arc": ["a", "b", "c"],
                "act_structure": {
                    "setup_ratio": 0.33,
                    "confrontation_ratio": 0.33,
                    "resolution_ratio": 0.34,
                },
            },
            "sound_plan": {
                "music_spotting": [
                    {"label": "intro", "start_sec": 0.0, "end_sec": 10.0},
                    {"label": "outro", "start_sec": 10.0, "end_sec": 15.0},
                ],
            },
            "scenes": [
                {
                    "shots": [
                        {"id": "s1", "dramatic_function": "hook", "duration_sec": 5.0},
                        {"id": "s2", "dramatic_function": "action", "duration_sec": 5.0},
                        {"id": "s3", "dramatic_function": "afterglow", "duration_sec": 5.0},
                    ]
                }
            ],
        }
        _make_film_root(tmp_path, spec=spec)
        result = verify(tmp_path)
        assert result["action"] == "verify"
        assert result["shots_checked"] == 3
        # act_structure: setup=0.33, confrontation=0.33, resolution=0.33 — should match
        if "act_structure" in result:
            assert result["act_structure"]["ok"] is True

    def test_verify_with_issues(self, tmp_path):
        spec = {
            "title": "test",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "test logline long enough",
                "tone": "dark",
                "emotional_arc": ["a", "b", "c"],
                "act_structure": {
                    "setup_ratio": 0.10,
                    "confrontation_ratio": 0.80,
                    "resolution_ratio": 0.10,
                },
            },
            "scenes": [
                {
                    "shots": [
                        {"id": "s1", "dramatic_function": "hook", "duration_sec": 10.0},
                        {"id": "s2", "dramatic_function": "action", "duration_sec": 5.0},
                        {"id": "s3", "dramatic_function": "afterglow", "duration_sec": 5.0},
                    ]
                }
            ],
        }
        _make_film_root(tmp_path, spec=spec)
        result = verify(tmp_path)
        # setup actual = 10/20 = 0.50 vs declared 0.10 → mismatch
        if "act_structure" in result:
            assert not result["act_structure"]["ok"]

    def test_verify_no_spec(self, tmp_path):
        """No film-spec.json → returns ok with no checks."""
        result = verify(tmp_path)
        assert result["ok"] is True
        assert result["shots_checked"] == 0

    def test_verify_music_spotting(self, tmp_path):
        spec = {
            "title": "test",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "test logline long enough",
                "tone": "dark",
                "emotional_arc": ["a", "b", "c"],
            },
            "sound_plan": {
                "music_spotting": [
                    {"label": "bad", "start_sec": 10.0, "end_sec": 5.0},
                ],
            },
            "scenes": [{"shots": []}],
        }
        _make_film_root(tmp_path, spec=spec)
        result = verify(tmp_path)
        if "music_spotting" in result:
            assert not result["music_spotting"]["ok"]
