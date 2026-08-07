"""F2 · face-lock triple + official-final plate honesty."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class FaceLockTripleTests(unittest.TestCase):
    def test_enroll_gap_blocks_master(self) -> None:
        from gates.face_lock_triple import audit_face_lock_triple

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps(
                    {
                        "cast_masters": {
                            "hero": "cast/hero.png",
                            "leon": "cast/leon.png",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            (root / "film-manifest.json").write_text(
                json.dumps({"clips": {}}), encoding="utf-8"
            )
            # No face-identity receipt → face leg hard
            rep = audit_face_lock_triple(root, write_receipt=True)
            self.assertFalse(rep.get("ok"))
            self.assertFalse(rep.get("master_eligible"))
            self.assertIn("face_identity", rep.get("hard_fail_legs") or [])
            self.assertTrue((root / "receipts" / "face-lock-triple.json").is_file())

    def test_unverified_partial_master_banned(self) -> None:
        from gates.face_lock_triple import audit_face_lock_triple

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
            (root / "film-manifest.json").write_text(
                json.dumps({"clips": {"s01": {"status": "approved", "path": "takes/s01.mp4"}}}),
                encoding="utf-8",
            )
            (root / "receipts" / "face-identity.json").write_text(
                json.dumps(
                    {
                        "verified": False,
                        "enrolled": {"hero": {}},
                        "audit": {"n_fail": 0},
                    }
                ),
                encoding="utf-8",
            )
            rep = audit_face_lock_triple(root)
            # soft face + identity_partial → ok may be true but master_eligible false
            self.assertFalse(rep.get("master_eligible"))
            self.assertTrue(rep.get("identity_partial"))

    def test_annotate_official_final_to_plate(self) -> None:
        from gates.face_lock_triple import annotate_official_final_for_face_lock, audit_face_lock_triple

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps(
                    {
                        "cast_masters": {
                            "hero": "cast/hero.png",
                            "leon": "cast/leon.png",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            (root / "film-manifest.json").write_text(
                json.dumps({"clips": {}}), encoding="utf-8"
            )
            (root / "receipts" / "official-final-report.json").write_text(
                json.dumps(
                    {
                        "status": "TECHNICAL_FINAL",
                        "master_lock": False,
                        "partial": False,
                    }
                ),
                encoding="utf-8",
            )
            trip = audit_face_lock_triple(root)
            out = annotate_official_final_for_face_lock(root, trip)
            self.assertTrue(out and out.get("updated"))
            body = json.loads(
                (root / "receipts" / "official-final-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(body.get("status"), "OFFICIAL_FINAL_PLATE")
            self.assertFalse(body.get("master_eligible"))
            self.assertIn("face_lock_triple", body.get("honest_limits") or [])

    def test_closeout_has_face_lock_triple_step(self) -> None:
        from closeout import closeout_status

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "out").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps(
                    {
                        "cast_masters": {
                            "hero": "cast/hero.png",
                            "villain": "cast/v.png",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            (root / "film-manifest.json").write_text(
                json.dumps({"clips": {}, "gates": {}}), encoding="utf-8"
            )
            # also manifest.json used by some closeout paths
            (root / "manifest.json").write_text(
                json.dumps({"gates": {}}), encoding="utf-8"
            )
            st = closeout_status(root)
            ids = [s["id"] for s in st.get("steps") or []]
            self.assertIn("face_lock_triple", ids)
            self.assertIn("transition_frame_audit", ids)
            fl = next(s for s in st["steps"] if s["id"] == "face_lock_triple")
            self.assertFalse(fl.get("ok"))
            self.assertIn("face_lock_triple", st)
            self.assertFalse(st["face_lock_triple"].get("master_eligible"))


if __name__ == "__main__":
    unittest.main()
