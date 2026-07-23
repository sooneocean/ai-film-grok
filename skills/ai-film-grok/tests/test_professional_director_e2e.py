"""End-to-end test: professional director system full chain.

init_production_book → update_department (lock visual) → impact_dry_run →
apply_stale_propagation → verify stale cascaded → validate_master_delivery
rejects an un-authorized final.

This is the integration glue the unit tests don't cover: each module is
tested in isolation, but the stale-propagation + master-gate chain has
to work across real file I/O and revision bumps.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from production_book import (  # noqa: E402
    ProductionBookConflict,
    apply_stale_propagation,
    impact_dry_run,
    init_production_book,
    read_production_book,
    update_department,
)
from master_delivery import validate_master_delivery  # noqa: E402

_SHA = "a" * 64


class ProfessionalDirectorE2E(unittest.TestCase):
    """Full chain: init → lock → stale propagate → master gate."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_full_chain_stale_propagates_and_master_gate_rejects(self) -> None:
        # 1. init production book — new project defaults to professional rigor
        book = init_production_book(self.root, title="e2e test", rigor="professional")
        self.assertEqual(book["rigor"], "professional")
        self.assertEqual(book["revision"], 1)
        self.assertIn("visual", book["departments"])
        # all departments start in draft
        for dep in book["departments"].values():
            self.assertEqual(dep["state"], "draft")

        # 2. lock the visual department (draft → review → locked)
        book = update_department(
            self.root,
            "visual",
            revision=1,
            content_sha256=_SHA,
            ref="style-bible.json",
            state="review",
            expected_revision=1,
        )
        self.assertEqual(book["revision"], 2)
        book = update_department(
            self.root,
            "visual",
            revision=1,
            content_sha256=_SHA,
            ref="style-bible.json",
            state="locked",
            expected_revision=2,
        )
        self.assertEqual(book["departments"]["visual"]["state"], "locked")
        self.assertEqual(book["revision"], 3)

        # 3. a downstream change (story) triggers impact dry-run
        book = read_production_book(self.root)
        impact = impact_dry_run(book, changed_refs=["story"], reason="beat spine revised")
        self.assertIn("visual", impact["affected"], "visual depends on story → must be affected")
        self.assertIn("affected", impact)

        # 4. apply stale propagation — affected departments go stale
        book = apply_stale_propagation(
            book,
            impact,
            expected_revision=3,
            transaction_id=impact["transaction_id"],
        )
        self.assertEqual(book["state"], "stale")
        self.assertEqual(book["revision"], 4)
        # visual was locked, now stale because story changed
        self.assertEqual(book["departments"]["visual"]["state"], "stale")
        self.assertTrue(book["departments"]["visual"]["stale_reasons"])
        # the stale reason is recorded at book level too
        self.assertTrue(book["stale_reasons"])

        # 5. optimistic-concurrency: a stale revision number must be rejected
        with self.assertRaises(ProductionBookConflict):
            apply_stale_propagation(
                read_production_book(self.root),
                impact,
                expected_revision=99,  # wrong revision
                transaction_id=impact["transaction_id"],
            )

        # 6. master gate: a delivery bound to the pre-stale hash is now invalid
        #    because the book revision moved on; with no real MP4 assets present
        #    the gate must reject outright.
        result = validate_master_delivery(
            self.root,
            delivery={
                "final_hash": _SHA,
                "assets": {},
                "human_approval": {"approved": False},
            },
        )
        self.assertFalse(result["ok"], "master gate must reject incomplete delivery")
        self.assertTrue(result["issues"], "rejection must carry issue details")


if __name__ == "__main__":
    unittest.main()
