"""Wave 4 · variety hard bulk + insert no silent T2V on meat."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class InsertNoSilentT2vTests(unittest.TestCase):
    def test_restricted_insert_without_still_is_i2v_not_t2v(self) -> None:
        from h3_mode import resolve_h3_mode

        r = resolve_h3_mode(
            {
                "id": "i1",
                "shot_role": "insert",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "shot_size": "l4",
            },
            intent={
                "content_class": "restricted_local",
                "shot_role": "insert",
                "heat_phase": "act",
            },
            has_still=False,
            has_last=False,
        )
        self.assertEqual(r["mode"], "i2v")
        self.assertIn("insert_needs_detail_still", r.get("reasons") or [])
        self.assertTrue(r.get("blocked") or r.get("block_code") == "INSERT_NEEDS_DETAIL_STILL")

    def test_soft_insert_without_still_may_t2v(self) -> None:
        from h3_mode import resolve_h3_mode

        r = resolve_h3_mode(
            {
                "id": "i2",
                "shot_role": "insert",
                "heat_phase": "setup",
                "wardrobe_state": "clothed",
            },
            intent={"shot_role": "insert", "content_class": "general"},
            has_still=False,
        )
        self.assertEqual(r["mode"], "t2v")

    def test_shot_lane_blocks_restricted_insert_no_still(self) -> None:
        from shot_lane import resolve_shot_lane

        r = resolve_shot_lane(
            {
                "id": "i3",
                "shot_role": "insert",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "shot_size": "l4",
            },
            has_still=False,
            has_last=False,
        )
        self.assertEqual(r["lane"], "insert")
        self.assertIn("INSERT_NEEDS_DETAIL_STILL", r.get("blocked_by") or [])
        self.assertFalse(r.get("i2v_allowed"))


class VarietyBulkHardTests(unittest.TestCase):
    def test_variety_precheck_low_poses_fails(self) -> None:
        from workflow_pack import variety_precheck

        root = Path(tempfile.mkdtemp())
        # 5 meat shots, all same pose → POSE_VARIETY_LOW
        shots = []
        for i in range(5):
            shots.append(
                {
                    "id": f"m{i}",
                    "heat_phase": "act",
                    "sex_pose": "missionary",
                    "shot_size": "ms",
                    "duration_sec": 5.2,
                    "dsl": {"motion": "thrust", "camera": {"move": "locked"}},
                }
            )
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "genre": "adult",
                    "heat_scale": "max",
                    "scenes": [{"shots": shots}],
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text("{}", encoding="utf-8")
        (root / "receipts").mkdir(exist_ok=True)
        rep = variety_precheck(root, write=True)
        self.assertFalse(rep.get("ok"))
        codes = {i.get("code") for i in rep.get("issues") or []}
        self.assertTrue(
            "POSE_VARIETY_LOW" in codes or "FACE_CU_LOW" in codes or "L4_INSERT_LOW" in codes,
            msg=str(codes),
        )


if __name__ == "__main__":
    unittest.main()
