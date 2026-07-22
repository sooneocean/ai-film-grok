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
            self.assertIsNotNone(packet.get("jobs_summary"))
            self.assertIn("total", packet["jobs_summary"] or {})


if __name__ == "__main__":
    unittest.main()
