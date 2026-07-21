#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from craft_spine import craft_status_report, detect_craft_stage  # noqa: E402
from selects_report import build_selects_report  # noqa: E402
from sound_plan import resolve_music_template  # noqa: E402


class CraftSpineTests(unittest.TestCase):
    def test_detect_on_emptyish_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
            craft = detect_craft_stage(root)
            self.assertIn(craft["craft_stage"], {
                "idea", "story", "beats", "shots", "media", "selects", "rough", "verified"
            })
            self.assertEqual(craft["stage_total"], 8)
            rep = craft_status_report(root)
            self.assertTrue(rep["ok"])
            self.assertIn("next_hint", rep)

    def test_selects_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps({"shots": [{"id": "shot01"}, {"id": "shot02"}]}) + "\n",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "clips": {
                            "shot01": {
                                "status": "approved",
                                "identity_approved": True,
                                "motion_approved": True,
                            }
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            rep = build_selects_report(root, write_receipt=True)
            self.assertEqual(rep["approved"], 1)
            self.assertEqual(rep["missing"], 1)
            self.assertFalse(rep["complete"])
            self.assertTrue(Path(rep["receipt_path"]).is_file())


class SkillBgmLibraryTests(unittest.TestCase):
    def test_skill_library_fallback(self) -> None:
        skill = Path(__file__).resolve().parents[1]
        bed_dir = skill / "assets" / "bgm" / "rnb"
        bed_dir.mkdir(parents=True, exist_ok=True)
        bed = bed_dir / "bed.wav"
        created = False
        if not bed.is_file():
            bed.write_bytes(b"RIFF" + b"\x00" * 512)
            created = True
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "audio").mkdir()
                resolved = resolve_music_template(root, mood="rnb", mode="auto")
                self.assertIsNotNone(resolved)
                assert resolved is not None
                self.assertEqual(resolved.get("source"), "skill_library")
        finally:
            if created and bed.is_file():
                bed.unlink()


if __name__ == "__main__":
    unittest.main()
