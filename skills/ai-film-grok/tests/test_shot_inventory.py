"""Shot inventory consistency — fail closed on partial sets."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from preflight import run_preflight  # noqa: E402
from shot_inventory import (  # noqa: E402
    InventoryError,
    assert_inventory_for_final,
    check_shot_inventory,
    flatten_shot_inventory,
)


def _write(root: Path, name: str, obj: dict) -> None:
    (root / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _spec_two_shots() -> dict:
    return {
        "title": "inventory-test",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "director_intent": {
            "logline": "雨夜后座升温的完整承诺句。",
            "tone": "测试",
            "emotional_arc": ["a", "b", "c"],
        },
        "sound_plan": {"mood": "rnb"},
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "话说她眨眼。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "blinks",
                            "motion": "soft blink, breath, idle not speaking",
                            "framing": (
                                "medium waist-up, full head, ample headroom, "
                                "safe framing no cropping"
                            ),
                        },
                    },
                    {
                        "id": "shot02",
                        "dramatic_function": "action",
                        "nar": "话说她落锁。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "locks door",
                            "motion": "hand turns latch shut, idle not speaking",
                            "framing": (
                                "medium full, full head and shoulders, "
                                "headroom, safe framing no cropping"
                            ),
                        },
                    },
                ]
            }
        ],
    }


class ShotInventoryTests(unittest.TestCase):
    def test_flatten_inventory_and_compare_exact_ids_not_just_count(self) -> None:
        planned = {"scenes": [{"shots": [{"id": "shot01"}, {"id": "shot02"}]}]}
        current = {
            "episodes": [{"scenes": [{"beats": [{"shots": [{"id": "shot01"}, {"id": "shot03"}]}]}]}]
        }
        self.assertEqual(flatten_shot_inventory(planned), ["shot01", "shot02"])
        report = check_shot_inventory(planned, current)
        self.assertFalse(report["ok"])
        self.assertEqual(report["shot_count"], report["approved_clip_count"])
        self.assertEqual(report["missing_clips"], ["shot02"])
        self.assertEqual(report["extra_clips"], ["shot03"])

    def test_complete_inventory_ok(self) -> None:
        report = check_shot_inventory(
            ["shot01", "shot02"],
            ["shot01", "shot02"],
        )
        self.assertTrue(report["ok"])
        self.assertTrue(report["complete"])
        self.assertFalse(report["partial"])

    def test_partial_inventory_not_ok(self) -> None:
        report = check_shot_inventory(
            ["shot01", "shot02"],
            ["shot01"],  # missing shot02
        )
        self.assertFalse(report["ok"])
        self.assertTrue(report["partial"])
        self.assertIn("shot02", report["missing_clips"])
        self.assertIn("INVENTORY_MISMATCH", report["codes"])

    def test_vo_mismatch_when_required(self) -> None:
        report = check_shot_inventory(
            ["shot01", "shot02"],
            ["shot01", "shot02"],
            vo_stem_ids=["shot01"],
            require_vo=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("VO_INVENTORY_MISMATCH", report["codes"])
        self.assertIn("shot02", report["missing_vo"])

    def test_assert_inventory_raises_on_partial(self) -> None:
        with self.assertRaises(InventoryError):
            assert_inventory_for_final(
                ["shot01", "shot02"],
                ["shot01"],
            )

    def test_preflight_hard_on_partial_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            _write(
                root,
                "manifest.json",
                {
                    "schema_version": 1,
                    "gates": {"clips_complete": False},
                    "clips": {
                        "shot01": {"status": "approved", "path": "clips/shot01.mp4"},
                        # shot02 missing
                    },
                    "outputs": {},
                },
            )
            _write(
                root,
                "style-bible.json",
                {"locked": True, "identity_lock": "ok"},
            )
            _write(root, "film-spec.json", _spec_two_shots())
            report = run_preflight(root)
            codes = {i["code"] for i in report["hard"]}
            self.assertIn("inventory_mismatch", codes)
            self.assertFalse(report["hard_ok"])
            inv = report.get("inventory") or {}
            self.assertTrue(inv.get("partial"))
            self.assertIn("shot02", inv.get("missing_clips") or [])


if __name__ == "__main__":
    unittest.main()
