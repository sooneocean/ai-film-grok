from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from subtitle_cut_boundaries import build_subtitle_cut_boundaries  # noqa: E402


class SubtitleCutBoundaryTests(unittest.TestCase):
    @pytest.mark.slow
    def test_rejects_cue_crossing_hard_or_continue_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final.srt").write_text(
                "1\n00:00:00,500 --> 00:00:01,500\n上一镜台词\n", encoding="utf-8"
            )
            (root / "timeline.json").write_text(
                json.dumps(
                    {"shots": [{"id": "a", "duration_sec": 1}, {"id": "b", "duration_sec": 1}]}
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "transition_intents": ["hard"],
                        "scenes": [{"shots": [{"id": "a"}, {"id": "b"}]}],
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(build_subtitle_cut_boundaries(root)["ok"])

    @pytest.mark.slow
    def test_allows_only_explicit_human_approved_carryover_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final.srt").write_text(
                "1\n00:00:00,500 --> 00:00:01,500\n电话声\n", encoding="utf-8"
            )
            (root / "timeline.json").write_text(
                json.dumps(
                    {"shots": [{"id": "a", "duration_sec": 1}, {"id": "b", "duration_sec": 1}]}
                ),
                encoding="utf-8",
            )
            spec = {
                "transition_intents": ["hard"],
                "subtitle_carryovers": [
                    {
                        "from_shot_id": "a",
                        "to_shot_id": "b",
                        "cue_start_sec": 0.5,
                        "cue_end_sec": 1.5,
                        "reason": "电话声作为 L-cut 延续",
                        "human_approved": True,
                    }
                ],
                "scenes": [{"shots": [{"id": "a"}, {"id": "b"}]}],
            }
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            report = build_subtitle_cut_boundaries(root)
            self.assertTrue(report["ok"], report)
            self.assertEqual(len(report["authorized_carryovers"]), 1)
