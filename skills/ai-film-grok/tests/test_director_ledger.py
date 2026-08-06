from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from director_ledger import build_director_ledger, ledger_is_current  # noqa: E402


class DirectorLedgerTests(unittest.TestCase):
    @pytest.mark.slow
    def test_carryover_approval_expires_when_spec_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            spec = {"subtitle_carryovers": [{"human_approved": True, "reason": "L-cut"}]}
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps({"outputs": {"final_film": {"sha256": "a"}}}), encoding="utf-8"
            )
            ledger = build_director_ledger(root)
            self.assertTrue(ledger["required"])
            self.assertTrue(ledger_is_current(root, ledger))
            (root / "film-spec.json").write_text(
                json.dumps({"subtitle_carryovers": []}), encoding="utf-8"
            )
            self.assertFalse(ledger_is_current(root, ledger))
