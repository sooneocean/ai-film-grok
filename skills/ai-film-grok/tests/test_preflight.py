"""preflight hard/soft gates from production lessons."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from preflight import run_preflight  # noqa: E402


def _write(root: Path, name: str, obj: dict) -> None:
    (root / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class PreflightTests(unittest.TestCase):
    def test_hard_on_loop_risk_and_ecchi_dark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            _write(
                root,
                "manifest.json",
                {"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}},
            )
            _write(
                root,
                "style-bible.json",
                {"locked": True, "identity_lock": "pink halo must be visible"},
            )
            # long nar → loop risk via _vo_budget
            _write(
                root,
                "film-spec.json",
                {
                    "title": "色气测试",
                    "vo_mode": "storyteller",
                    "tts_backend": "edge",
                    "director_intent": {
                        "logline": "雨夜后座升温的完整承诺句。",
                        "tone": "色气·诱惑",
                        "emotional_arc": ["a", "b", "c"],
                    },
                    "sound_plan": {"mood": "dark"},
                    "_vo_budget": {"loop_risk_shots": ["shot01"]},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "dramatic_function": "hook",
                                    "nar": "字" * 40,
                                    "duration_sec": 6,
                                    "dsl": {
                                        "subject": "a",
                                        "action": "b",
                                        "motion": "slow push-in, soft blink, idle not speaking",
                                    },
                                }
                            ]
                        }
                    ],
                },
            )
            report = run_preflight(root)
            codes = {i["code"] for i in report["hard"]}
            self.assertIn("loop_risk", codes)
            self.assertIn("ecchi_dark_bgm", codes)
            self.assertFalse(report["hard_ok"])

    def test_soft_compose_preview_when_clips_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            _write(
                root,
                "manifest.json",
                {
                    "schema_version": 1,
                    "gates": {"clips_complete": True},
                    "clips": {"shot01": {"status": "approved"}},
                    "outputs": {},
                },
            )
            _write(
                root,
                "style-bible.json",
                {"locked": True, "identity_lock": "ok"},
            )
            _write(
                root,
                "film-spec.json",
                {
                    "title": "预览软提示",
                    "vo_mode": "storyteller",
                    "tts_backend": "edge",
                    "director_intent": {
                        "logline": "测试 compose-preview soft 提示的完整句子。",
                        "tone": "测试",
                        "emotional_arc": ["a", "b", "c"],
                    },
                    "sound_plan": {"mood": "rnb"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "dramatic_function": "hook",
                                    "nar": "话说她眨眼。",
                                    "duration_sec": 6,
                                    "dsl": {
                                        "subject": "a",
                                        "action": "b",
                                        "motion": "slow push-in, soft blink, idle not speaking",
                                    },
                                }
                            ]
                        }
                    ],
                },
            )
            report = run_preflight(root)
            soft_codes = {i["code"] for i in report["soft"]}
            self.assertIn("compose_preview_recommended", soft_codes)

    def test_soft_pilot_and_tts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            _write(root, "manifest.json", {"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}})
            _write(root, "style-bible.json", {"locked": True, "identity_lock": "halo"})
            _write(
                root,
                "film-spec.json",
                {
                    "title": "日常",
                    "vo_mode": "storyteller",
                    "tts_backend": "auto",
                    "director_intent": {
                        "logline": "普通日常故事的完整一句话。",
                        "tone": "日常",
                        "emotional_arc": ["a", "b", "c"],
                    },
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "dramatic_function": "hook",
                                    "nar": "话说夜里。",
                                    "duration_sec": 6,
                                    "dsl": {
                                        "subject": "a",
                                        "action": "b",
                                        "motion": "slow push-in, soft blink, idle not speaking",
                                    },
                                }
                            ]
                        }
                    ],
                },
            )
            report = run_preflight(root)
            soft_codes = {i["code"] for i in report["soft"]}
            self.assertTrue(report["hard_ok"])
            self.assertIn("pilot_not_user_approved", soft_codes)
            self.assertIn("tts_external_risk", soft_codes)


if __name__ == "__main__":
    unittest.main()
