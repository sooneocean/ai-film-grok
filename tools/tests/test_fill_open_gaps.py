#!/usr/bin/env python3
"""Unit tests for tools/fill_open_gaps.py (the open fill-gap closer).

Focuses on the pure classification in eligible() (closeable vs dead-end)
and the dry-run contract of main() (no writes without --apply). The
end-to-end --apply path is covered by tools/self_test.py on a temp copy.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fill_open_gaps  # noqa: E402


def _cat(statuses):
    return {"schema": "x", "revision": 1,
            "assets": {aid: {"status": s} for aid, s in statuses.items()}}


def _fill_gap(gap_id, sid, status="open"):
    return {"gap_id": gap_id, "action": "fill", "status": status,
            "suggested_asset_id": sid}


class EligibleTest(unittest.TestCase):
    def test_approved_candidate_is_closeable(self):
        cat = _cat({"a1": "approved"})
        gaps = [_fill_gap("g1", "a1")]
        closeable, dead = fill_open_gaps.eligible(gaps, cat)
        self.assertEqual([g["gap_id"] for g in closeable], ["g1"])
        self.assertEqual(dead, [])

    def test_pending_candidate_is_dead_end(self):
        cat = _cat({"a1": "pending_human_review"})
        gaps = [_fill_gap("g1", "a1")]
        closeable, dead = fill_open_gaps.eligible(gaps, cat)
        self.assertEqual(closeable, [])
        self.assertEqual([g["gap_id"] for g in dead], ["g1"])

    def test_missing_asset_is_dead_end(self):
        cat = _cat({})  # no assets at all
        gaps = [_fill_gap("g1", "ghost")]
        closeable, dead = fill_open_gaps.eligible(gaps, cat)
        self.assertEqual(closeable, [])
        self.assertEqual([g["gap_id"] for g in dead], ["g1"])

    def test_missing_suggested_id_is_dead_end(self):
        cat = _cat({"a1": "approved"})
        g = {"gap_id": "g1", "action": "fill", "status": "open"}  # no suggested_asset_id
        closeable, dead = fill_open_gaps.eligible([g], cat)
        self.assertEqual(closeable, [])
        self.assertEqual([g["gap_id"] for g in dead], ["g1"])

    def test_already_filled_excluded(self):
        cat = _cat({"a1": "approved"})
        gaps = [_fill_gap("g1", "a1", status="filled")]
        closeable, dead = fill_open_gaps.eligible(gaps, cat)
        self.assertEqual(closeable, [])
        self.assertEqual(dead, [])

    def test_generate_gap_excluded(self):
        cat = _cat({"a1": "approved"})
        g = {"gap_id": "g1", "action": "generate", "status": "open",
             "suggested_asset_id": "a1"}
        closeable, dead = fill_open_gaps.eligible([g], cat)
        self.assertEqual(closeable, [])
        self.assertEqual(dead, [])

    def test_mixed_backlog_split(self):
        cat = _cat({"a1": "approved", "a2": "pending_human_review", "a3": "approved"})
        gaps = [
            _fill_gap("g1", "a1"),          # closeable
            _fill_gap("g2", "a2"),          # dead-end (pending)
            _fill_gap("g3", "missing"),     # dead-end (missing)
            _fill_gap("g4", "a3", status="filled"),  # excluded
            {"gap_id": "g5", "action": "generate", "status": "open",
             "suggested_asset_id": "a1"},   # excluded (generate)
        ]
        closeable, dead = fill_open_gaps.eligible(gaps, cat)
        self.assertEqual({g["gap_id"] for g in closeable}, {"g1"})
        self.assertEqual({g["gap_id"] for g in dead}, {"g2", "g3"})


class DryRunContractTest(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        tmp = tempfile.mkdtemp()
        catp = os.path.join(tmp, "catalog.json")
        gapsp = os.path.join(tmp, "gap-queue.jsonl")
        json.dump(_cat({"a1": "approved"}), open(catp, "w"), indent=2)
        with open(gapsp, "w", encoding="utf-8") as f:
            f.write(json.dumps(_fill_gap("g1", "a1"), ensure_ascii=False) + "\n")

        old_cat, old_gap = fill_open_gaps.CAT, fill_open_gaps.GAP
        fill_open_gaps.CAT, fill_open_gaps.GAP = catp, gapsp
        try:
            with patch.object(sys, "argv", ["fill_open_gaps.py"]):
                fill_open_gaps.main()
            # unchanged on disk
            cat2 = json.load(open(catp, encoding="utf-8"))
            gaps2 = [json.loads(l) for l in open(gapsp, encoding="utf-8") if l.strip()]
            self.assertEqual(cat2["revision"], 1)
            self.assertEqual(gaps2[0]["status"], "open")
        finally:
            fill_open_gaps.CAT, fill_open_gaps.GAP = old_cat, old_gap


if __name__ == "__main__":
    unittest.main(verbosity=2)
