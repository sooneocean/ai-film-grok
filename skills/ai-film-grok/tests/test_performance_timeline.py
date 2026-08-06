from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from performance_timeline import build_performance_timeline  # noqa: E402


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PerformanceTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "receipts" / "reviews").mkdir(parents=True)
        (self.root / "film-spec.json").write_text(
            json.dumps(
                {
                    "content_channels_strict": True,
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "content_channels": {
                                        "performance": {"playable_action": "她后退一步"},
                                        "motion": {"scene_trigger": "门铃响起"},
                                    },
                                },
                                {
                                    "id": "shot02",
                                    "content_channels": {
                                        "performance": {"reaction_trigger": "手机亮起"}
                                    },
                                },
                            ]
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.root / "timeline.json").write_text(
            json.dumps(
                {
                    "shots": [
                        {"id": "shot01", "duration_sec": 2},
                        {"id": "shot02", "duration_sec": 3},
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _frame(self, name: str) -> dict[str, str]:
        path = self.root / "receipts" / "reviews" / f"{name}.jpg"
        path.write_bytes(name.encode())
        return {"path": str(path), "sha256": _hash(path)}

    def _receipt(self, shot_id: str, evidence: dict[str, dict[str, object]]) -> None:
        (self.root / "receipts" / "reviews" / f"{shot_id}.json").write_text(
            json.dumps({"approved": True, "performance_contract": {"evidence": evidence}}),
            encoding="utf-8",
        )

    @pytest.mark.slow
    def test_orders_human_observations_across_shots_and_binds_frames(self) -> None:
        self._receipt(
            "shot01",
            {
                "trigger_visible": {
                    "timestamp_sec": 0.2,
                    "note": "门铃响起",
                    "frame": self._frame("a"),
                },
                "action_visible": {
                    "timestamp_sec": 0.8,
                    "note": "她后退",
                    "frame": self._frame("b"),
                },
            },
        )
        self._receipt(
            "shot02",
            {
                "trigger_visible": {
                    "timestamp_sec": 0.5,
                    "note": "手机亮起",
                    "frame": self._frame("c"),
                },
                "reaction_visible": {
                    "timestamp_sec": 1.1,
                    "note": "她收紧肩膀",
                    "frame": self._frame("d"),
                },
            },
        )
        report = build_performance_timeline(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            [event["film_timestamp_sec"] for event in report["events"]], [0.2, 0.8, 2.5, 3.1]
        )
        self.assertTrue(Path(report["path"]).is_file())

    @pytest.mark.slow
    def test_rejects_missing_or_stale_evidence_frame(self) -> None:
        frame = self._frame("gone")
        self._receipt(
            "shot01",
            {
                "trigger_visible": {"timestamp_sec": 0.2, "note": "门铃响起", "frame": frame},
                "action_visible": {
                    "timestamp_sec": 0.8,
                    "note": "她后退",
                    "frame": self._frame("still"),
                },
            },
        )
        frame_path = Path(frame["path"])
        frame_path.unlink()
        report = build_performance_timeline(self.root)
        self.assertFalse(report["ok"])
        self.assertIn(
            "PERFORMANCE_EVIDENCE_FRAME_MISSING", {item["code"] for item in report["errors"]}
        )
