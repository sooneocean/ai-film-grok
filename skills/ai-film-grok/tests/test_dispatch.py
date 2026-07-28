#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dispatch import build_dispatch  # noqa: E402


def test_dispatch_defers_scene_sound_until_audio_timeline_exists(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t","theme":"x"}\n', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "t",
                "shots": [{"id": "shot01", "action": "她走到门边，推门进入。"}],
            }
        ),
        encoding="utf-8",
    )
    packet = build_dispatch(tmp_path, gates={}, include_capability=False, write_receipt=False)
    assert packet["scene_sound"]["status"] == "blocked"
    assert any(action["id"] == "scene-sound-plan" for action in packet["next_actions"])
    assert packet["next_id"] != "scene-sound-plan"


def test_dispatch_promotes_scene_sound_after_timed_audio_projection(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t","theme":"x"}\n', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "t",
                "audio_timeline_v1": {"duration_sec": 4.0, "events": []},
                "shots": [
                    {
                        "id": "shot01",
                        "duration_sec": 4.0,
                        "action": "她走到门边，推门进入。",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    packet = build_dispatch(
        tmp_path,
        gates={
            "brief": True,
            "style_locked": True,
            "spec": True,
            "clips_complete": True,
        },
        include_capability=False,
        write_receipt=False,
    )
    assert packet["scene_sound"]["status"] == "blocked"
    assert packet["next_id"] == "scene-sound-plan"


@pytest.mark.slow
class DispatchTests(unittest.TestCase):
    @pytest.mark.slow
    def test_dispatch_packet_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text('{"title":"t","theme":"x"}\n', encoding="utf-8")
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "title": "t",
                        "tts_backend": "edge",
                        "shots": [{"id": "shot01", "nar": "话说", "dramatic_function": "hook"}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            packet = build_dispatch(
                root,
                gates={},
                include_capability=True,
                write_receipt=True,
            )
            self.assertTrue(packet.get("ok"))
            self.assertIn("craft_stage", packet)
            self.assertIn("next_actions", packet)
            self.assertIn("agent_do", packet)
            self.assertIn("routing", packet)
            self.assertTrue(Path(packet["receipt_path"]).is_file())
            self.assertEqual(packet["routing"].get("tts_default"), "edge")
            self.assertIn("off", packet["routing"].get("lipsync", ""))
            # Phase 1+2 additive fields
            self.assertGreaterEqual(int(packet.get("schema_version") or 0), 2)
            self.assertIn("jobs_summary", packet)
            self.assertIn("execution_plan_digest", packet)
            self.assertIn("graph", packet)
            self.assertIsNotNone(packet.get("next_action"))
            self.assertTrue(packet["next_action"].get("argv"))
            self.assertFalse(str(packet.get("next_cmd") or "").lstrip().startswith("#"))
            self.assertIsNotNone(packet.get("jobs_summary"))
            self.assertIn("total", packet["jobs_summary"] or {})
            self.assertEqual(
                packet.get("generation_usage", {}).get("tracking_status"),
                "tracking_not_started",
            )
            self.assertEqual(packet.get("generation_usage", {}).get("requests_total"), 0)


if __name__ == "__main__":
    unittest.main()
