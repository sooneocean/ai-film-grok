"""F3 · still face-lock bind."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class StillFaceLockBindTests(unittest.TestCase):
    def test_archive_path_hard(self) -> None:
        from gates.still_face_lock_bind import check_still_face_lock_bind

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps({"cast_masters": {"hero": "cast/hero.png"}}),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            (root / "receipts" / "face-identity.json").write_text(
                json.dumps({"enrolled": {"hero": {"fingerprint": {"ahash": 1}}}}),
                encoding="utf-8",
            )
            still = root / "takes" / "_archive_old" / "s01.png"
            still.parent.mkdir(parents=True)
            still.write_bytes(b"x")
            rep = check_still_face_lock_bind(
                root, still, {"id": "s01", "cast": ["hero"]}
            )
            self.assertFalse(rep.get("ok"))
            self.assertIn("STILL_FACE_ARCHIVE_PATH", rep.get("codes") or [])

    def test_not_enrolled_hard(self) -> None:
        from gates.still_face_lock_bind import check_still_face_lock_bind

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps({"cast_masters": {"hero": "cast/hero.png"}}),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            (root / "receipts" / "face-identity.json").write_text(
                json.dumps({"enrolled": {}}), encoding="utf-8"
            )
            still = root / "stills" / "s01.png"
            still.parent.mkdir(parents=True)
            still.write_bytes(b"x")
            rep = check_still_face_lock_bind(
                root, still, {"id": "s01", "cast": ["hero"]}
            )
            self.assertFalse(rep.get("ok"))
            self.assertIn("STILL_FACE_NOT_ENROLLED", rep.get("hard_codes") or [])

    def test_not_enrolled_soft_opt_out(self) -> None:
        from gates.still_face_lock_bind import check_still_face_lock_bind

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps({"cast_masters": {"hero": "cast/hero.png"}}),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text(
                json.dumps({"face_identity_soft": True}), encoding="utf-8"
            )
            (root / "receipts" / "face-identity.json").write_text(
                json.dumps({"enrolled": {}}), encoding="utf-8"
            )
            still = root / "stills" / "s01.png"
            still.parent.mkdir(parents=True)
            still.write_bytes(b"x")
            rep = check_still_face_lock_bind(
                root, still, {"id": "s01", "cast": ["hero"]}
            )
            self.assertTrue(rep.get("ok"))
            self.assertTrue(rep.get("soft"))


class PlateTransitionAlignTests(unittest.TestCase):
    def test_align_rewrites_mismatch(self) -> None:
        from plan.plate_transition_align import align_story_styles_to_transition_ops

        ops = [
            {"picture": {"base": "xfade", "style": "dissolve"}},
            {"picture": {"base": "hard_cut", "style": "none"}},
        ]
        styles = ["fade", "smoothleft"]
        aligned, issues = align_story_styles_to_transition_ops(ops, styles)
        self.assertEqual(aligned[0], "dissolve")
        self.assertTrue(any(i["code"] == "PLATE_TRANSITION_STYLE_MISMATCH" for i in issues))

    def test_continue_not_hard_reported(self) -> None:
        from plan.plate_transition_align import plate_transition_ops_alignment_report

        rep = plate_transition_ops_alignment_report(
            transition_ops=[
                {
                    "continuity_class": "continue",
                    "picture": {"base": "xfade", "style": "fade"},
                }
            ],
            story_styles=["fade"],
        )
        self.assertFalse(rep.get("ok"))
        self.assertIn("PLATE_TRANSITION_CONTINUE_NOT_HARD", rep.get("hard_codes") or [])


if __name__ == "__main__":
    unittest.main()
