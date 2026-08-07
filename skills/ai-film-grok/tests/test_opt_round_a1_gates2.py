"""Optimization round 2 · A1 cinematic/preflight silent-green fixes."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestCinematicVarietyFailClosed(unittest.TestCase):
    def test_variety_probe_exception_not_green(self) -> None:
        from cinematic_gate import run_cinematic_gate

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "heat_scale": "max",
                    "scenes": [
                        {
                            "shots": [
                                {"id": "a1", "heat_phase": "act", "duration_sec": 5},
                                {"id": "a2", "heat_phase": "act", "duration_sec": 5},
                            ]
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")

        with mock.patch(
            "workflow_pack.variety_precheck",
            side_effect=RuntimeError("boom variety"),
        ):
            rep = run_cinematic_gate(
                root,
                write=False,
                run_ship_prep=False,
                skip_variety=False,
                skip_five_track=True,
                auto_i2v=False,
            )
        var_steps = [s for s in (rep.get("steps") or []) if s.get("id") == "variety"]
        self.assertTrue(var_steps)
        self.assertFalse(var_steps[0].get("ok"))
        self.assertTrue(var_steps[0].get("hard"))


class TestPreflightSpeakerProbeHard(unittest.TestCase):
    def test_speaker_probe_error_hard_on_max_dialogue(self) -> None:
        # Direct unit of severity logic via preflight run with mocked lint
        from preflight import run_preflight

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "title": "t",
                    "vo_mode": "dialogue_drama",
                    "heat_scale": "max",
                    "adult_max_iron": True,
                    "scenes": [{"shots": [{"id": "s1", "heat_phase": "setup", "duration_sec": 5}]}],
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps({"gates": {}, "clips": {}, "stills": {}}),
            encoding="utf-8",
        )

        with mock.patch(
            "dialogue_speaker_frame_gate.lint_dialogue_speaker_frame",
            side_effect=RuntimeError("lint exploded"),
        ):
            rep = run_preflight(root)
        hard = [i for i in (rep.get("hard") or []) if isinstance(i, dict)]
        soft = [i for i in (rep.get("soft") or []) if isinstance(i, dict)]
        hard_codes = {str(i.get("code")) for i in hard}
        self.assertIn(
            "speaker_frame_probe_error",
            hard_codes,
            msg=f"hard={hard_codes} soft={[i.get('code') for i in soft][:15]}",
        )
        for i in hard:
            if i.get("code") == "speaker_frame_probe_error":
                self.assertEqual(i.get("level"), "hard")
                break


if __name__ == "__main__":
    unittest.main()
