"""H3 · table-driven production gates (meaning / zero_nar / motion ship).

One matrix file so genre × escape × fail-mode regressions stay visible in the
fast suite. Complements (does not replace) test_dramatic_meaning /
test_zero_narration_gate / test_delivery_truth.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from dramatic_meaning import meaning_gate_enabled  # noqa: E402
from film_spec import zero_narration_gate  # noqa: E402
from i2v_motion_gate import I2VMotionGateError, assert_i2v_final_gate_for_export  # noqa: E402
from production_gates import ProductionGateError, assert_heat_allows_final  # noqa: E402

# ── meaning_gate_enabled ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "spec,env_skip,expected",
    [
        ({}, False, True),
        ({"heat_scale": "soft"}, False, True),
        ({"heat_scale": "medium"}, False, True),
        ({"heat_scale": "max"}, False, True),
        ({"quality_target": "premium_vertical"}, False, True),
        ({"genre": "suspense"}, False, True),
        ({"dramatic_meaning_strict": False}, False, False),
        ({"dramatic_meaning_strict": True}, False, True),
        # env skip: only explicit strict:true still on
        ({"heat_scale": "max"}, True, False),
        ({"dramatic_meaning_strict": True}, True, True),
        ({"dramatic_meaning_strict": False}, True, False),
        (None, False, True),
    ],
    ids=[
        "empty_default_on",
        "soft_on",
        "medium_on",
        "max_on",
        "premium_on",
        "genre_suspense_on",
        "explicit_false",
        "explicit_true",
        "env_skip_max_off",
        "env_skip_strict_true_wins",
        "env_skip_strict_false",
        "none_spec_on",
    ],
)
def test_meaning_gate_table(spec, env_skip, expected) -> None:
    env = {"AIFILM_SKIP_MEANING_GATE": "1"} if env_skip else {}
    with mock.patch.dict(os.environ, env, clear=False):
        if not env_skip:
            os.environ.pop("AIFILM_SKIP_MEANING_GATE", None)
        assert meaning_gate_enabled(spec) is expected


# ── zero_narration_gate ──────────────────────────────────────────────────────


def _zn_spec(
    *,
    vo_mode: str = "dialogue_drama",
    zero_narration_strict: bool | None = None,
    shots: list[dict] | None = None,
) -> dict:
    spec: dict = {
        "title": "zn-matrix",
        "vo_mode": vo_mode,
        "scenes": [
            {
                "id": "sc01",
                "shots": shots
                or [
                    {
                        "id": "sh01",
                        "spoken_text": "你回来了。",
                        "speaker": "女主",
                        "screen_mode": "on_camera",
                    }
                ],
            }
        ],
    }
    if zero_narration_strict is not None:
        spec["zero_narration_strict"] = zero_narration_strict
    return spec


@pytest.mark.parametrize(
    "builder_kwargs,expect_ok,expect_code",
    [
        ({}, True, None),
        (
            {
                "shots": [
                    {
                        "id": "sh01",
                        "nar": "她独自站在雨中。",
                    }
                ]
            },
            False,
            "NAR_BUDGET_VIOLATION",
        ),
        (
            {
                "shots": [
                    {
                        "id": "sh01",
                        "spoken_text": "谁？",
                        "speaker": "男主",
                        "screen_mode": "on_camera",
                    },
                    {"id": "sh02", "nar": "时间停住了。"},
                ]
            },
            False,
            "NAR_BUDGET_VIOLATION",
        ),
        (
            {
                "zero_narration_strict": False,
                "shots": [{"id": "sh01", "nar": "说书旁白"}],
            },
            True,
            None,
        ),
        (
            {
                "vo_mode": "narration",
                "shots": [{"id": "sh01", "nar": "旁白模式允许"}],
            },
            True,
            None,
        ),
    ],
    ids=[
        "dialogue_only_pass",
        "pure_nar_fail",
        "mixed_nar_fail",
        "escape_strict_false",
        "non_dialogue_drama_allows_nar",
    ],
)
def test_zero_narration_table(builder_kwargs, expect_ok, expect_code) -> None:
    result = zero_narration_gate(_zn_spec(**builder_kwargs))
    assert result["ok"] is expect_ok
    if expect_code:
        assert result.get("code") == expect_code


# ── motion ship (export gate) ────────────────────────────────────────────────


class MotionShipGateTableTests(unittest.TestCase):
    def test_motion_ship_matrix(self) -> None:
        cases = [
            # (receipt_payload, env_skip, expect_ok, expect_raise)
            (None, False, False, True),
            ({"ok": False, "kind": "i2v-final-gate"}, False, False, True),
            ({"ok": True, "kind": "i2v-final-gate"}, False, True, False),
            (None, True, True, False),
        ]
        for payload, env_skip, expect_ok, expect_raise in cases:
            with self.subTest(payload=payload, env_skip=env_skip):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "receipts").mkdir()
                    if payload is not None:
                        (root / "receipts" / "i2v-final-gate.json").write_text(
                            json.dumps(payload), encoding="utf-8"
                        )
                    env = {"AIFILM_SKIP_I2V_MOTION_GATE": "1"} if env_skip else {}
                    with mock.patch.dict(os.environ, env, clear=False):
                        if not env_skip:
                            os.environ.pop("AIFILM_SKIP_I2V_MOTION_GATE", None)
                        if expect_raise:
                            with self.assertRaises(I2VMotionGateError):
                                assert_i2v_final_gate_for_export(root)
                        else:
                            out = assert_i2v_final_gate_for_export(root)
                            self.assertEqual(bool(out.get("ok")), expect_ok)


# ── heat final gate (production_gates) ───────────────────────────────────────


class HeatFinalGateTableTests(unittest.TestCase):
    def test_heat_final_matrix(self) -> None:
        cases = [
            # (status, expect_raise_substr)
            (
                {
                    "active": True,
                    "hard_fail": True,
                    "final_ok": False,
                    "needs_boost": True,
                    "score": 10,
                    "grade": "D",
                    "why": "impact too low",
                },
                "heat final gate",
            ),
            (
                {
                    "active": True,
                    "hard_fail": False,
                    "final_ok": True,
                    "score": 80,
                    "grade": "A",
                },
                None,
            ),
            (
                {"active": False, "ok": True, "hard_fail": False},
                None,
            ),
        ]
        for status, err_sub in cases:
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with mock.patch("heat_check.heat_agent_status", return_value=status):
                        if err_sub:
                            with self.assertRaises(ProductionGateError) as ctx:
                                assert_heat_allows_final(root, env_skip=False)
                            self.assertIn(err_sub, str(ctx.exception).lower())
                        else:
                            # may return None or dict — must not raise
                            assert_heat_allows_final(root, env_skip=False)


if __name__ == "__main__":
    unittest.main()
