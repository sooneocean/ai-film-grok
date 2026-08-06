from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import select_fill_idle_mode  # noqa: E402

pytestmark = pytest.mark.hotpath


def _res(mode="i2v", alt_mode=None):
    return {"mode": mode, "alt_mode": alt_mode, "reasons": [f"base:{mode}"]}


class SelectFillIdleModeTests(unittest.TestCase):
    # --- primary dual second leg: R2V = energy lane -------------------------

    def test_primary_dual_need_r2v_picks_r2v(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("i2v"),
            reasons=["dual_need_r2v"],
            lane="primary_h3",
            status="pending",
            primary=True,
            has_last=False,
            on_cam_close=False,
        )
        self.assertEqual(mode, "r2v")
        self.assertEqual(added, ["dual_second_leg_r2v"])

    def test_primary_dual_need_i2v_prefers_flf_when_last(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("i2v"),
            reasons=["dual_need_i2v"],
            lane="primary_h3",
            status="pending",
            primary=True,
            has_last=True,
            on_cam_close=False,
        )
        self.assertEqual(mode, "flf")
        self.assertEqual(added, ["dual_second_leg_flf"])

    def test_primary_dual_need_i2v_falls_back_i2v_without_last(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("i2v"),
            reasons=["dual_need_i2v"],
            lane="primary_h3",
            status="pending",
            primary=True,
            has_last=False,
            on_cam_close=False,
        )
        self.assertEqual(mode, "i2v")
        self.assertEqual(added, ["dual_second_leg_i2v"])

    # --- P2 soft challenge: face-lock preferred over blind r2v ---------------

    def test_p2_challenge_prefers_flf_over_r2v(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("r2v", alt_mode="i2v"),
            reasons=["fill_idle_challenge"],
            lane="challenge_grok",
            status="pending",
            primary=False,
            has_last=True,
            on_cam_close=False,
        )
        self.assertEqual(mode, "flf")
        self.assertEqual(added, ["p2_prefer_flf_face_pk"])

    def test_p2_challenge_prefers_i2v_without_last(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("r2v", alt_mode="i2v"),
            reasons=["fill_idle_challenge"],
            lane="challenge_grok",
            status="pending",
            primary=False,
            has_last=False,
            on_cam_close=False,
        )
        self.assertEqual(mode, "i2v")
        self.assertEqual(added, ["p2_prefer_i2v_face_pk"])

    def test_p2_challenge_keeps_r2v_for_dialogue_close_energy(self):
        # Genuine on-camera close energy: keep r2v, no added reason.
        mode, added = select_fill_idle_mode(
            mode_res=_res("r2v", alt_mode="i2v"),
            reasons=["fill_idle_challenge"],
            lane="challenge_grok",
            status="pending",
            primary=False,
            has_last=True,
            on_cam_close=True,
        )
        self.assertEqual(mode, "r2v")
        self.assertEqual(added, [])

    def test_p2_challenge_keeps_r2v_when_alt_not_face(self):
        # alt_mode is r2v (true energy, no face-lock alternative): keep r2v.
        mode, added = select_fill_idle_mode(
            mode_res=_res("r2v", alt_mode="r2v"),
            reasons=["fill_idle_challenge"],
            lane="challenge_grok",
            status="pending",
            primary=False,
            has_last=True,
            on_cam_close=False,
        )
        self.assertEqual(mode, "r2v")
        self.assertEqual(added, [])

    # --- passthrough: no mode override --------------------------------------

    def test_passthrough_when_primary_without_dual_reason(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("flf", alt_mode="i2v"),
            reasons=["restricted_primary"],
            lane="primary_h3",
            status="pending",
            primary=True,
            has_last=True,
            on_cam_close=True,
        )
        self.assertEqual(mode, "flf")
        self.assertEqual(added, [])

    def test_passthrough_non_primary_non_challenge(self):
        mode, added = select_fill_idle_mode(
            mode_res=_res("i2v", alt_mode="r2v"),
            reasons=["has_baseline_take"],
            lane="challenge_grok",
            status="done",
            primary=False,
            has_last=True,
            on_cam_close=False,
        )
        # status does not start with "pending" -> no override.
        self.assertEqual(mode, "i2v")
        self.assertEqual(added, [])

    def test_default_mode_fallback_when_missing(self):
        mode, added = select_fill_idle_mode(
            mode_res={},
            reasons=[],
            lane="skip",
            status="skip",
            primary=False,
            has_last=False,
            on_cam_close=False,
        )
        self.assertEqual(mode, "i2v")
        self.assertEqual(added, [])


if __name__ == "__main__":
    unittest.main()
