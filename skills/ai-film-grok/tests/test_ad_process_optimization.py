"""AD process optimization · duration density / shortlist discipline / scale promote gate."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestDurationDensityLift(unittest.TestCase):
    def test_heat_lift_without_enough_shots(self) -> None:
        from plan.duration_target import finalize_duration_density

        dens = finalize_duration_density(
            target_duration_requested=30.0,
            target_duration_effective=60.0,
            heat_target_lift="hardcore",
            actual_shot_count=5,
        )
        self.assertEqual(dens["suggested_min_shots_h3"], 12)  # ceil(60/5.2)
        self.assertEqual(dens["shots_n_delta"], 7)
        self.assertFalse(dens["ok"])
        self.assertEqual(dens["action_required"], "add_shots_or_cut_promise")
        self.assertIn("ADULT_TARGET_LIFT_WITHOUT_SHOTS", dens["codes"])

    def test_density_ok_when_enough_shots(self) -> None:
        from plan.duration_target import finalize_duration_density

        dens = finalize_duration_density(
            target_duration_requested=60.0,
            target_duration_effective=60.0,
            heat_target_lift=None,
            actual_shot_count=12,
        )
        self.assertTrue(dens["ok"])
        self.assertEqual(dens["shots_n_delta"], 0)
        self.assertTrue(dens["density_ok"])


class TestSelectShortlistDiscipline(unittest.TestCase):
    def test_receipt_has_mean_only_forbidden(self) -> None:
        from workflow_pack import select_shortlist

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "takes" / "s1").mkdir(parents=True)
            # two fake takes (empty files ok for list path; scoring soft)
            (root / "takes" / "s1" / "a.mp4").write_bytes(b"\x00" * 200)
            (root / "takes" / "s1" / "b.mp4").write_bytes(b"\x00" * 200)
            (root / "film-spec.json").write_text(
                json.dumps({"scenes": [{"shots": [{"id": "s1"}]}]}),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, {"AIFILM_SKIP_ANTI_HIJACK": "1"}, clear=False):
                out = select_shortlist(root, write=True, promote=False, measure_missing=False)
            self.assertTrue(out.get("mean_only_forbidden"))
            self.assertEqual(out.get("schema_version"), 2)
            self.assertIn("composition_discipline", out)
            if out.get("multi_take_count", 0) >= 2:
                self.assertIn("SHORTLIST_MEAN_ONLY_NO_ANTI_HIJACK", out.get("codes") or [])


class TestScalePromoteBanNote(unittest.TestCase):
    def test_decide_scale_promote_ban_shape(self) -> None:
        from narrative.scale_fallback import decide_scale_fallback

        d = decide_scale_fallback(
            target_tier="bare",
            consecutive_poison=3,
            consecutive_anatomy_fail=0,
            hard_on_threshold=2,
        )
        self.assertTrue(d.get("promote_ban"))
        self.assertIn("SCALE_HARD_ON_BAN", d.get("codes") or [])


if __name__ == "__main__":
    unittest.main()
