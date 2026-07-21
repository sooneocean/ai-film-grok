"""Production gates: pilot user-approval + loop-risk hard blocks."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import RECOMMENDED_NAR_CHARS  # noqa: E402
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_no_loop_risk,
    assert_pilot_user_approved,
    loop_risk_shots_from_spec,
    pilot_is_user_approved,
)


class PilotGateTests(unittest.TestCase):
    def test_agent_self_approve_rejected(self) -> None:
        self.assertFalse(
            pilot_is_user_approved(
                {"approved": True, "approved_by": "agent", "notes": "self"}
            )
        )

    def test_user_approve_ok(self) -> None:
        self.assertTrue(
            pilot_is_user_approved(
                {"approved": True, "approved_by": "user", "user_phrase": "pilot 过"}
            )
        )

    def test_assert_requires_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            with self.assertRaisesRegex(ProductionGateError, "missing|pilot"):
                assert_pilot_user_approved(root, env_skip=False)

    def test_allows_three_then_blocks_fourth(self) -> None:
        from production_gates import assert_pilot_allows_add

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            known: set[str] = set()
            for i in range(1, 4):
                sid = f"shot0{i}"
                assert_pilot_allows_add(
                    root, shot_id=sid, existing_shot_ids=known, env_skip=False
                )
                known.add(sid)
            with self.assertRaisesRegex(ProductionGateError, "pilot"):
                assert_pilot_allows_add(
                    root, shot_id="shot04", existing_shot_ids=known, env_skip=False
                )

    def test_assert_accepts_user_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "receipts"
            rec.mkdir()
            (rec / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "pilot 过",
                        "shots": ["shot01", "shot02", "shot03"],
                    }
                ),
                encoding="utf-8",
            )
            out = assert_pilot_user_approved(root, env_skip=False)
            self.assertTrue(out.get("ok"))


class LoopRiskGateTests(unittest.TestCase):
    def test_long_nar_is_risk(self) -> None:
        spec = {
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "nar": "字" * 40,
                            "duration_sec": 6,
                        }
                    ]
                }
            ]
        }
        risk = loop_risk_shots_from_spec(spec)
        self.assertIn("shot01", risk)

    def test_short_nar_ok(self) -> None:
        spec = {
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "nar": "夜深，她推门进来。",
                            "duration_sec": 6,
                        }
                    ]
                }
            ]
        }
        self.assertEqual(loop_risk_shots_from_spec(spec), [])
        self.assertLessEqual(len("夜深，她推门进来。"), RECOMMENDED_NAR_CHARS + 5)

    def test_assert_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # minimal invalid for validate — use force path with prebuilt risk via direct assert
            with self.assertRaises(ProductionGateError):
                assert_no_loop_risk(
                    spec={
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "shot09",
                                        "nar": "旁" * 36,
                                        "duration_sec": 6,
                                    }
                                ]
                            }
                        ]
                    },
                    env_skip=False,
                )


if __name__ == "__main__":
    unittest.main()
