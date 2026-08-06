"""Wave H: bulk-preflight receipt reuse + select-shortlist wiring."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from advance import ADVANCE_ACTIONS  # noqa: E402
from workflow_pack import assert_bulk_preflight  # noqa: E402


class BulkPreflightReuseTests(unittest.TestCase):
    def test_reuses_green_receipt_when_spec_not_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "film-spec.json").write_text('{"title": "x"}', encoding="utf-8")
            rec = root / "receipts" / "bulk-preflight.json"
            rec.write_text(
                json.dumps({"ok": True, "kind": "bulk-preflight", "failed": []}),
                encoding="utf-8",
            )
            # ensure receipt mtime >= spec
            time.sleep(0.02)
            rec.write_text(
                json.dumps({"ok": True, "kind": "bulk-preflight", "failed": []}),
                encoding="utf-8",
            )
            with mock.patch(
                "workflow_pack.bulk_preflight",
                side_effect=AssertionError("should not re-run"),
            ):
                out = assert_bulk_preflight(root, require=True)
            self.assertTrue(out.get("ok"))
            self.assertTrue(out.get("reused"))

    def test_reruns_when_spec_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            rec = root / "receipts" / "bulk-preflight.json"
            rec.write_text(json.dumps({"ok": True}), encoding="utf-8")
            time.sleep(0.02)
            (root / "film-spec.json").write_text('{"title": "y"}', encoding="utf-8")
            with mock.patch(
                "workflow_pack.bulk_preflight",
                return_value={"ok": True, "failed": [], "next_cmd": None},
            ) as bp:
                out = assert_bulk_preflight(root, require=True)
            bp.assert_called_once()
            self.assertTrue(out.get("ok"))


class SelectShortlistWiringTests(unittest.TestCase):
    def test_advance_has_select_shortlist(self) -> None:
        self.assertIn("select-shortlist", ADVANCE_ACTIONS)

    def test_dispatch_source_mentions_wave_h(self) -> None:
        src = (SCRIPTS / "spine" / "dispatch.py").read_text(encoding="utf-8")
        self.assertIn("select-shortlist", src)


if __name__ == "__main__":
    unittest.main()
