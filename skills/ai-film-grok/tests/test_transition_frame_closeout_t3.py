"""T3 · transition frame audit closeout status."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TransitionFrameCloseoutTests(unittest.TestCase):
    def test_no_final_skipped_ok(self) -> None:
        from transition_frame_audit import transition_frame_audit_closeout_status

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            out = transition_frame_audit_closeout_status(root, write_receipt=True)
            self.assertTrue(out.get("ok"))
            self.assertTrue(out.get("skipped"))
            self.assertEqual(out.get("codes") or [], [])

    def test_final_missing_audit_hard(self) -> None:
        from transition_frame_audit import transition_frame_audit_closeout_status
        from util import sha256_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "out").mkdir()
            (root / "receipts").mkdir()
            final = root / "out" / "film_final.mp4"
            final.write_bytes(b"final-bytes")
            (root / "out" / "final-delivery.json").write_text(
                json.dumps(
                    {
                        "output_sha256": sha256_file(final),
                        "fps": 24,
                        "duration_sec": 5,
                        "transition": {
                            "operations": [],
                            "film_timeline": {"shot_starts": [0]},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            out = transition_frame_audit_closeout_status(root, write_receipt=True)
            self.assertFalse(out.get("ok"))
            self.assertIn("TRANSITION_FRAME_AUDIT_MISSING", out.get("codes") or [])

    def test_soft_opt_out(self) -> None:
        from transition_frame_audit import transition_frame_audit_closeout_status
        from util import sha256_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "out").mkdir()
            (root / "receipts").mkdir()
            final = root / "out" / "film_final.mp4"
            final.write_bytes(b"final-bytes")
            (root / "out" / "final-delivery.json").write_text(
                json.dumps(
                    {
                        "output_sha256": sha256_file(final),
                        "fps": 24,
                        "duration_sec": 5,
                        "transition": {
                            "operations": [],
                            "film_timeline": {"shot_starts": [0]},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text(
                json.dumps({"transition_policy_soft": True}), encoding="utf-8"
            )
            out = transition_frame_audit_closeout_status(root)
            self.assertTrue(out.get("ok"))
            self.assertTrue(out.get("soft"))
            self.assertIn("TRANSITION_FRAME_AUDIT_MISSING", out.get("codes") or [])


if __name__ == "__main__":
    unittest.main()
