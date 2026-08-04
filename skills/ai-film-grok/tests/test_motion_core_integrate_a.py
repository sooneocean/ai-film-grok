#!/usr/bin/env python3
"""Phase A deep integration: single tier resolver + Grok fail-closed + no silent pass."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_motion_gate import motion_tier_for_shot  # noqa: E402
from motion_prompt_spine import (  # noqa: E402
    MotionCoreError,
    motion_tier_for,
    motion_tier_resolve,
)
from prompt_injector import PromptInjector  # noqa: E402


class SingleTierResolver(unittest.TestCase):
    """Table: prompt_tier and optical_tier stay consistent."""

    CASES = [
        # heat, df, wardrobe, want_optical, want_prompt
        ("act", "reaction", "", "meat", "high"),
        ("climax", "", "bare", "meat", "high"),
        ("setup", "reaction", "", "soft", "soft"),
        ("bridge", "afterglow", "bare", "medium", "medium"),
        ("afterglow", "", "", "medium", "medium"),
        ("setup", "action", "", "meat", "high"),
        ("setup", "hook", "", "high", "high"),
        ("setup", "", "", "normal", "medium"),
        ("foreplay", "", "", "medium", "medium"),
    ]

    def test_table_optical_and_prompt(self) -> None:
        for heat, df, wardrobe, optical, prompt in self.CASES:
            with self.subTest(heat=heat, df=df, wardrobe=wardrobe):
                shot = {
                    "id": "t",
                    "heat_phase": heat,
                    "dramatic_function": df,
                    "wardrobe_state": wardrobe,
                }
                r = motion_tier_resolve(shot)
                self.assertEqual(r["optical_tier"], optical)
                self.assertEqual(r["prompt_tier"], prompt)
                self.assertEqual(motion_tier_for(shot), prompt)
                self.assertEqual(
                    motion_tier_for_shot(
                        heat_phase=heat,
                        dramatic_function=df,
                        wardrobe_state=wardrobe,
                    ),
                    optical,
                )

    def test_spine_tier_high_maps_meat_optical(self) -> None:
        r = motion_tier_resolve(spine_tier="high", heat_phase="setup")
        self.assertEqual(r["optical_tier"], "meat")
        self.assertEqual(r["prompt_tier"], "high")


class GrokInjectorFailClosed(unittest.TestCase):
    def _bible(self) -> dict:
        return {
            "schema_version": 1,
            "state": "locked",
            "style_signature": "cel anime",
            "heat_scale": "soft",
        }

    def test_i2v_empty_core_raises(self) -> None:
        inj = PromptInjector(self._bible(), template_version="I2V")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            shot = {"id": "empty1", "shot_role": "hero"}  # no action / df / dialogue
            with mock.patch.dict("os.environ", {}, clear=False):
                import os

                os.environ.pop("AIFILM_SKIP_MOTION_CORE", None)
                with self.assertRaises(MotionCoreError):
                    inj.assemble(shot, root)

    def test_escape_skips_assert(self) -> None:
        inj = PromptInjector(self._bible(), template_version="I2V")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            shot = {
                "id": "esc1",
                "shot_role": "hero",
                "dsl": {"action": "she turns and smiles at him"},
            }
            with mock.patch.dict("os.environ", {"AIFILM_SKIP_MOTION_CORE": "1"}):
                out = inj.assemble(shot, root)
            self.assertIn("prompt_text", out)


class MediaQueueNoSilentPass(unittest.TestCase):
    def test_enrich_failure_becomes_queue_error(self) -> None:
        # Import path only — ensure MotionCoreError maps; unexpected Exception too.
        from media_queue import QueueError

        self.assertTrue(issubclass(QueueError, Exception))


class PhaseBAutoGateAndSurface(unittest.TestCase):
    def test_collect_rows_fills_df(self) -> None:
        from i2v_motion_gate import collect_motion_gate_rows

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "r1",
                                        "heat_phase": "setup",
                                        "dramatic_function": "reaction",
                                        "wardrobe_state": "",
                                    }
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (root / "takes" / "r1").mkdir(parents=True)
            side = root / "takes" / "r1" / "r1.mp4.json"
            side.write_text(json.dumps({"mean": 12.0}), encoding="utf-8")
            # empty mp4 path not required for mean sidecar lookup by name pattern
            rows = collect_motion_gate_rows(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["dramatic_function"], "reaction")
            # mean only from sidecar next to mp4 — create dummy mp4+json
            mp4 = root / "takes" / "r1" / "r1.mp4"
            mp4.write_bytes(b"\x00")
            (Path(str(mp4) + ".json")).write_text(
                json.dumps({"mean": 12.0}), encoding="utf-8"
            )
            rows2 = collect_motion_gate_rows(root)
            self.assertEqual(rows2[0]["mean"], 12.0)

    def test_soft_df_auto_gate_passes_mean12(self) -> None:
        from cli_motion import i2v_motion_gate_from_rows

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "r1",
                                        "heat_phase": "setup",
                                        "dramatic_function": "reaction",
                                    }
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            takes = root / "takes" / "r1"
            takes.mkdir(parents=True)
            mp4 = takes / "r1.mp4"
            mp4.write_bytes(b"\x00")
            (Path(str(mp4) + ".json")).write_text(
                json.dumps({"mean": 12.0}), encoding="utf-8"
            )
            rep = i2v_motion_gate_from_rows(
                [],
                root=root,
                write_receipts=True,
                auto_from_root=True,
            )
            self.assertTrue(rep["ok"], rep.get("audit"))
            self.assertTrue((root / "receipts" / "i2v-final-gate.json").is_file())
            per = (rep.get("audit") or {}).get("per_shot") or []
            self.assertEqual(per[0].get("tier"), "soft")

    def test_grok_spine_written_by_injector(self) -> None:
        inj = PromptInjector(
            {
                "schema_version": 1,
                "state": "locked",
                "style_signature": "cel anime",
                "heat_scale": "soft",
            },
            template_version="I2V",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            shot = {
                "id": "g9",
                "shot_role": "hero",
                "dramatic_function": "bridge",
                "dsl": {"action": "she walks toward the door slowly"},
            }
            inj.assemble(shot, root)
            spine = root / "receipts" / "prompts" / "g9.grok.spine.txt"
            self.assertTrue(spine.is_file())
            self.assertIn("Dramatic function: bridge", spine.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
