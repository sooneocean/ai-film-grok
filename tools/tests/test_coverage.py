#!/usr/bin/env python3
"""Unit tests for tools/coverage.py (supply/demand analyzer + emit)."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coverage  # noqa: E402


def _cat(statuses):
    # statuses: {id: (status, mood, stem, energy)}
    return {"schema": "x", "revision": 1,
            "assets": {aid: {"status": s, "mood": m, "stem_profile": st, "energy": e}
                       for aid, (s, m, st, e) in statuses.items()}}


def _gap(mood, stem, energy, status, action="generate"):
    return {"gap_id": f"g-{mood}-{stem}-{energy}-{status}", "action": action,
            "status": status, "mood": mood, "stem_profile": stem, "energy": energy}


class AnalyzeTest(unittest.TestCase):
    def test_classify_ok_thin_starved_and_inflight(self):
        cat = _cat({
            "a1": ("approved", "rnb", "full", 0.5),
            "a2": ("approved", "rnb", "full", 0.5),
        })
        gaps = [
            _gap("rnb", "full", 0.5, "filled"),     # demand 2, approved 2 -> eff 2 < target4 => THIN
            _gap("rnb", "full", 0.5, "filled"),
            _gap("ambient", "pad", 0.2, "routed_generate"),  # inflight 1, demand 1 (bucket low)
            _gap("ambient", "pad", 0.2, "open"),               # demand 2 total
            _gap("sad", "pad", 0.2, "open"),                   # STARVED: 0 appr/inflight
        ]
        a = coverage.analyze(cat, gaps, target_min=4)
        by = {(r["mood"], r["stem"], r["energy_bucket"]): r for r in a["rows"]}
        rnb = by[("rnb", "full", "mid")]
        self.assertEqual(rnb["approved"], 2)
        self.assertEqual(rnb["inflight"], 0)
        self.assertEqual(rnb["demand"], 2)
        self.assertEqual(rnb["effective"], 2)
        self.assertEqual(rnb["status"], "THIN")  # eff(2) < target_min(4)
        amb = by[("ambient", "pad", "low")]
        self.assertEqual(amb["approved"], 0)
        self.assertEqual(amb["inflight"], 1)     # in-flight counted
        self.assertEqual(amb["effective"], 1)
        self.assertEqual(amb["status"], "THIN")  # eff(1) < target_min(4)
        sad = by[("sad", "pad", "low")]
        self.assertEqual(sad["approved"], 0)
        self.assertEqual(sad["inflight"], 0)
        self.assertEqual(sad["status"], "STARVED")

    def test_priority_queue_orders_by_deficit_and_caps(self):
        cat = _cat({"a1": ("approved", "rnb", "full", 0.5)})
        gaps = [
            _gap("rnb", "full", 0.5, "filled"),       # demand1 eff1 -> THIN, deficit0
            _gap("sad", "pad", 0.2, "open"),          # STARVED deficit1
            _gap("tense", "pulse", 0.8, "open"),      # STARVED deficit1
        ]
        a = coverage.analyze(cat, gaps, target_min=4)
        pq = coverage.priority_queue(a, max_total=5)
        # sad & tense deficit=1 each -> emit target_min - 0 = 4 each, but capped
        # to max_total 5 total => 4 + 1 (one truncated). Order by deficit desc,
        # then by emit count desc (stable among equal deficits).
        total = sum(n for _, n in pq)
        self.assertLessEqual(total, 5)
        emit_map = {(r["mood"], r["stem"], r["energy_bucket"]): n for r, n in pq}
        self.assertIn(("sad", "pad", "low"), emit_map)
        self.assertIn(("tense", "pulse", "high"), emit_map)
        # rnb is only THIN via target_min but deficit 0; still may appear with emit 3,
        # ensure total respects cap and sad/tense (deficit 1) come first.
        self.assertEqual(pq[0][0]["deficit"], 1)


class EmitTest(unittest.TestCase):
    def _setup(self, tmp):
        catp = os.path.join(tmp, "catalog.json")
        gapsp = os.path.join(tmp, "gap-queue.jsonl")
        togenp = os.path.join(tmp, "to-generate.jsonl")
        json.dump(_cat({
            "a1": ("approved", "rnb", "full", 0.5),
            "a2": ("approved", "rnb", "full", 0.5),
        }), open(catp, "w"), indent=2)
        gaps = [_gap("rnb", "full", 0.5, "filled"), _gap("rnb", "full", 0.5, "filled"),
                _gap("ambient", "pad", 0.35, "open")]
        with open(gapsp, "w", encoding="utf-8") as f:
            for g in gaps:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")
        open(togenp, "w").close()  # empty ledger
        return catp, gapsp, togenp

    def _run_main(self, tmp, *argv):
        catp, gapsp, togenp = self._setup(tmp)
        old = (coverage.CAT, coverage.GAP, coverage.TOGEN)
        coverage.CAT, coverage.GAP, coverage.TOGEN = catp, gapsp, togenp
        try:
            with patch.object(sys, "argv", ["coverage.py", *argv]):
                coverage.main()
        finally:
            coverage.CAT, coverage.GAP, coverage.TOGEN = old
        return gapsp, togenp

    def test_dry_run_writes_nothing(self):
        tmp = tempfile.mkdtemp()
        gapsp, togenp = self._run_main(tmp, "--emit-generate", "--target-min", "4")
        lines = [l for l in open(gapsp, encoding="utf-8") if l.strip()]
        self.assertEqual(len(lines), 3)  # unchanged (2 filled + 1 open ambient)
        self.assertEqual(os.path.getsize(togenp), 0)
        self.assertFalse(os.path.exists(gapsp + ".bak"))

    def test_apply_writes_gaps_and_togen_with_backup(self):
        tmp = tempfile.mkdtemp()
        gapsp, togenp = self._run_main(tmp, "--emit-generate", "--apply", "--target-min", "4")
        gaps = [json.loads(l) for l in open(gapsp, encoding="utf-8") if l.strip()]
        cov = [g for g in gaps if g.get("reason") == "coverage_gap"]
        self.assertTrue(cov)
        for g in cov:
            self.assertEqual(g["action"], "generate")
            self.assertEqual(g["status"], "open")
            self.assertIsNone(g["suggested_asset_id"])
        togen = [json.loads(l) for l in open(togenp, encoding="utf-8") if l.strip()]
        self.assertEqual(len(togen), len(cov))
        self.assertTrue(os.path.exists(gapsp + ".bak"))
        self.assertTrue(os.path.exists(togenp + ".bak"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
