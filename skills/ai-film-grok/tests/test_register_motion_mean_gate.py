"""register-clip motion mean gate evaluate_shot_motion floors."""

from __future__ import annotations

from i2v_motion_gate import MEAN_MEAT_FLOOR, MEAN_NORMAL_FLOOR, evaluate_shot_motion


def test_meat_mean_low():
    g = evaluate_shot_motion(5.0, heat_phase="act", shot_id="s1")
    assert g["ok"] is False
    assert g["floor"] == MEAN_MEAT_FLOOR
    assert "I2V_MEAT_MEAN_LOW" in g["codes"]


def test_normal_ok():
    g = evaluate_shot_motion(MEAN_NORMAL_FLOOR + 1.0, heat_phase="setup", shot_id="s2")
    assert g["ok"] is True
