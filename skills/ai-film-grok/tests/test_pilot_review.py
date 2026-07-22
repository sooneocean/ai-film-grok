"""Pilot pick / scorecard / user-approve gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pilot_review import (  # noqa: E402
    PilotReviewError,
    build_pilot_approval,
    build_pilot_scorecard,
    pick_pilot_shots,
    pilot_report,
    pilot_scorecard_ready,
    user_phrase_is_approval,
    write_pilot_scorecard,
)
from production_gates import pilot_is_user_approved  # noqa: E402


def _spec_three() -> dict:
    return {
        "title": "pilot-test",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "测试 pilot 三镜 scorecard 的完整句子。",
            "tone": "测试",
            "emotional_arc": ["a", "b", "c"],
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "话说。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "b",
                            "motion": "slow push-in, soft blink, idle not speaking",
                        },
                    },
                    {
                        "id": "shot02",
                        "dramatic_function": "bridge",
                        "nar": "然后。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "b",
                            "motion": "slow push-in, soft blink, idle not speaking",
                        },
                    },
                    {
                        "id": "shot03",
                        "dramatic_function": "reaction",
                        "nar": "她眨眼。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "b",
                            "motion": "soft blink, breathing, idle not speaking",
                        },
                    },
                    {
                        "id": "shot04",
                        "dramatic_function": "action",
                        "nar": "靠近。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "b",
                            "motion": "slow push-in, lean closer, idle not speaking",
                        },
                    },
                ]
            }
        ],
    }


class PilotPickTests(unittest.TestCase):
    def test_prefer_hook_reaction_action(self) -> None:
        shots = pick_pilot_shots(_spec_three(), n=3)
        self.assertEqual(shots, ["shot01", "shot03", "shot04"])


class PilotScorecardTests(unittest.TestCase):
    def test_all_pass_and_write(self) -> None:
        card = build_pilot_scorecard(
            shots=["shot01", "shot03", "shot04"],
            scores={"identity": True, "style": True, "motion": True},
            reviewer="dex",
            notes="face/style/motion ok",
        )
        self.assertTrue(card["all_pass"])
        self.assertTrue(pilot_scorecard_ready(card))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            path = write_pilot_scorecard(root, card)
            self.assertTrue(path.is_file())

    def test_fail_dimension(self) -> None:
        card = build_pilot_scorecard(
            shots=["shot01"],
            scores={"identity": True, "style": False, "motion": True},
            reviewer="dex",
            notes="style drift",
        )
        self.assertFalse(card["all_pass"])
        self.assertEqual(card["failures"], ["style"])


class PilotApproveTests(unittest.TestCase):
    def test_rejects_agent_phrase(self) -> None:
        with self.assertRaises(PilotReviewError):
            build_pilot_approval(
                shots=["shot01"],
                user_phrase="looks fine to me as agent",
                scorecard={
                    "kind": "pilot-scorecard",
                    "dimensions": {"identity": True, "style": True, "motion": True},
                },
            )

    def test_accepts_pilot_guo(self) -> None:
        scorecard = {
            "kind": "pilot-scorecard",
            "dimensions": {"identity": True, "style": True, "motion": True},
        }
        approval = build_pilot_approval(
            shots=["shot01", "shot03", "shot04"],
            user_phrase="pilot 过，可以批量",
            scorecard=scorecard,
        )
        self.assertTrue(approval["approved"])
        self.assertEqual(approval["approved_by"], "user")
        self.assertTrue(pilot_is_user_approved(approval))

    def test_require_scorecard(self) -> None:
        with self.assertRaisesRegex(PilotReviewError, "scorecard"):
            build_pilot_approval(
                shots=["shot01"],
                user_phrase="pilot 过",
                scorecard=None,
                require_scorecard=True,
            )

    def test_user_phrase_markers(self) -> None:
        from pilot_review import user_phrase_wants_run_to_completion

        self.assertTrue(user_phrase_is_approval("pilot 过"))
        self.assertTrue(user_phrase_is_approval("可以量产"))
        self.assertTrue(user_phrase_is_approval("可以"))
        self.assertTrue(user_phrase_is_approval("可以 以后这个动作 直接进行到生成完成"))
        self.assertTrue(user_phrase_is_approval("ok"))
        self.assertFalse(user_phrase_is_approval("继续生成"))
        self.assertFalse(user_phrase_is_approval("可以改一下"))
        self.assertFalse(user_phrase_is_approval("不行重做"))
        self.assertTrue(user_phrase_wants_run_to_completion("可以 以后这个动作 直接进行到生成完成"))
        self.assertFalse(user_phrase_wants_run_to_completion("pilot 过"))


class PilotReportTests(unittest.TestCase):
    def test_report_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("receipts", "clips", "keyframes"):
                (root / name).mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(_spec_three(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 1, "stills": {}, "clips": {}, "outputs": {}}),
                encoding="utf-8",
            )
            report = pilot_report(root)
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["shots"]), 3)
            self.assertFalse(report["user_approved"])
            self.assertTrue(any("pilot-score" in n or "register" in n for n in report["next"]))


if __name__ == "__main__":
    unittest.main()
