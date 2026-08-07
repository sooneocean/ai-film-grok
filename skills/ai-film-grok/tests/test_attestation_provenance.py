"""Honesty-rail R2 · human attestation provenance."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestAttestationProvenance(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("AIFILM_REVIEWER", None)
        os.environ.pop("AIFILM_AGENT_SESSION", None)

    def test_happy_full_provenance(self) -> None:
        from core.attestation_audit import write_attestation, find_attestation, provenance_fields

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_REVIEWER"] = "dex"
            os.environ["AIFILM_AGENT_SESSION"] = "sess-1"
            still = root / "keyframes" / "s01.jpg"
            still.parent.mkdir(parents=True)
            still.write_bytes(b"x")
            write_attestation(
                root,
                kind="anatomy_still",
                shot_id="s01",
                still_path=still,
                anatomy_safe=True,
            )
            entry = find_attestation(root, kind="anatomy_still", shot_id="s01")
            assert entry is not None
            fields = provenance_fields(entry)
            for k in ("agent_session", "reviewer", "timestamp", "still_path"):
                self.assertTrue(fields.get(k), msg=f"missing {k}")
            self.assertTrue(entry.get("provenance_complete"))
            self.assertFalse(entry.get("pending_human_review"))
            ledger = root / "receipts" / "attestation-ledger.json"
            self.assertTrue(ledger.is_file())
            data = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(data.get("count"), 1)

    def test_missing_reviewer_pending(self) -> None:
        from core.attestation_audit import write_attestation, verify_attestation_ledger

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # no reviewer / session env
            write_attestation(
                root,
                kind="anatomy_still",
                shot_id="s02",
                still_path=root / "k.jpg",
                anatomy_safe=True,
            )
            ver = verify_attestation_ledger(root)
            self.assertEqual(ver.get("pending_count"), 1)
            self.assertTrue(ver.get("ok"))  # advisory never hard-fail
            pending = ver.get("pending_human_review") or []
            self.assertEqual(pending[0].get("shot_id"), "s02")

    def test_require_anatomy_safe_writes_ledger(self) -> None:
        from anatomy_safety import require_anatomy_safe

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # non-adult film → anatomy not required; still True writes ledger when flagged
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            require_anatomy_safe(
                root=root,
                anatomy_safe=True,
                kind="still",
                shot_id="s03",
                still_path=root / "x.jpg",
                reviewer="dex",
                agent_session="sess-2",
            )
            from core.attestation_audit import find_attestation

            entry = find_attestation(root, kind="anatomy_still", shot_id="s03")
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertTrue(entry.get("provenance_complete"))


if __name__ == "__main__":
    unittest.main()
