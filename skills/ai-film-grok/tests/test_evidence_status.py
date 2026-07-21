"""Evidence separation: intent vs executed vs human review."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evidence_status import classify_evidence  # noqa: E402


def _write(root: Path, rel: str, obj: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class EvidenceStatusTests(unittest.TestCase):
    def test_sound_plan_is_intent_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "e",
                    "sound_plan": {"mood": "rnb", "bed": True},
                    "transition_intents": ["hard", "soft"],
                },
            )
            _write(root, "manifest.json", {"schema_version": 1, "clips": {}, "outputs": {}})
            ev = classify_evidence(root)
            self.assertTrue(ev["intent"]["sound_plan"])
            self.assertTrue(ev["intent"]["transition_intents"])
            self.assertFalse(ev["executed"]["mix_report"])
            self.assertFalse(ev["executed"]["final_film"])
            codes = {r["code"] for r in ev["impersonation_risks"]}
            self.assertIn("SOUND_PLAN_NOT_EXECUTED", codes)

    def test_tts_rehearsal_marks_executed_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", {"title": "e"})
            _write(root, "manifest.json", {"schema_version": 1, "clips": {}, "outputs": {}})
            _write(
                root,
                "receipts/tts-rehearsal.json",
                {
                    "ok": True,
                    "shot_count": 1,
                    "shots": [{"shot_id": "shot01", "measured_duration_sec": 2.0}],
                    "evidence_class": "executed_audio",
                },
            )
            ev = classify_evidence(root)
            self.assertTrue(ev["executed"]["tts_rehearsal"])
            self.assertEqual(ev["executed"]["class"], "executed")
            self.assertEqual(ev["human_review"]["class"], "human_review")
            self.assertEqual(ev["intent"]["class"], "intent")

    def test_final_stub_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", {"title": "e"})
            _write(
                root,
                "manifest.json",
                {
                    "schema_version": 1,
                    "clips": {},
                    "outputs": {
                        "final_film": {
                            "path": "out/missing_final.mp4",
                            # no sha, no qa, file does not exist
                        }
                    },
                },
            )
            ev = classify_evidence(root)
            self.assertFalse(ev["executed"]["final_film"])
            codes = {r["code"] for r in ev["impersonation_risks"]}
            self.assertIn("FINAL_STUB", codes)


if __name__ == "__main__":
    unittest.main()
