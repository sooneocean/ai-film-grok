"""next_actions routing + pilot fail → director_notes."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from next_actions import (  # noqa: E402
    build_next_actions,
    detect_pipeline_stage,
    format_stage_line,
    persist_pipeline_stage,
)
from pilot_review import (  # noqa: E402
    build_pilot_scorecard,
    fail_scorecard_to_director_notes,
    write_pilot_scorecard,
)
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_pilot_allows_add,
)


class NextActionsTests(unittest.TestCase):
    def test_suggests_write_spec_when_no_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            actions = build_next_actions(root, gates={"brief": True, "style_locked": True})
            ids = [a["id"] for a in actions]
            self.assertIn("write-spec", ids)
            self.assertIn("pilot-report", ids)

    def test_suggests_review_when_final_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            man = {
                "outputs": {
                    "final_film": {
                        "path": "film_final.mp4",
                        "sha256": "abc",
                        "post_engine": "ffmpeg",
                    }
                }
            }
            (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
            actions = build_next_actions(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            ids = [a["id"] for a in actions]
            self.assertIn("review-final", ids)

    def test_clips_complete_prefers_preview_before_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "receipts").mkdir()
            (root / "receipts" / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "可以",
                        "shots": ["shot01", "shot02", "shot03"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(json.dumps({"outputs": {}}), encoding="utf-8")
            actions = build_next_actions(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            ids = [a["id"] for a in actions]
            self.assertIn("tts-rehearse", ids)
            self.assertIn("compose-preview", ids)
            self.assertIn("final", ids)
            self.assertLess(ids.index("tts-rehearse"), ids.index("final"))
            self.assertLess(ids.index("compose-preview"), ids.index("final"))

    def test_after_preview_receipt_prefers_designed_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"outputs": {}}), encoding="utf-8")
            (root / "receipts").mkdir()
            (root / "receipts" / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "可以",
                        "shots": ["shot01", "shot02", "shot03"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "receipts" / "compose-preview.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "url": "http://localhost:3002",
                        "kind": "compose-preview-receipt",
                    }
                ),
                encoding="utf-8",
            )
            actions = build_next_actions(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            ids = [a["id"] for a in actions]
            self.assertIn("tts-rehearse", ids)
            self.assertIn("final-designed", ids)
            # rehearse before designed final; designed final still recommended over plain FFmpeg
            self.assertLess(ids.index("tts-rehearse"), ids.index("final-designed"))
            designed = next(a for a in actions if a["id"] == "final-designed")
            self.assertIn("hyperframes", designed["cmd"])


class PipelineStageTests(unittest.TestCase):
    """Product spine: agent → visual → voice → design → post → deliver → done."""

    def test_agent_when_spec_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            stage = detect_pipeline_stage(
                root, gates={"brief": True, "style_locked": True, "spec": False}
            )
            self.assertEqual(stage["stage"], "agent")
            self.assertIn("write-spec", stage["detail"])
            self.assertEqual(stage["stage_total"], 7)

    def test_voice_when_clips_complete_no_rehearse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "receipts").mkdir()
            (root / "receipts" / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "可以",
                        "shots": ["shot01", "shot02", "shot03"],
                    }
                ),
                encoding="utf-8",
            )
            stage = detect_pipeline_stage(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            self.assertEqual(stage["stage"], "voice")
            self.assertEqual(stage["detail"], "tts-rehearse")
            self.assertTrue(stage["checklist"]["visual"])
            self.assertFalse(stage["checklist"]["voice"])

    def test_design_after_rehearse_and_preview_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "receipts").mkdir()
            (root / "receipts" / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "可以",
                        "shots": ["shot01"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "receipts" / "tts-rehearsal.json").write_text(
                json.dumps({"ok": True, "shots": {"shot01": {"sec": 3.0}}, "shot_count": 1}),
                encoding="utf-8",
            )
            stage = detect_pipeline_stage(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            self.assertEqual(stage["stage"], "design")
            self.assertEqual(stage["detail"], "compose-preview")

    def test_post_when_final_film_awaits_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "outputs": {
                            "final_film": {
                                "path": "film_final.mp4",
                                "sha256": "abc",
                                "post_engine": "hyperframes",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            stage = detect_pipeline_stage(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            self.assertEqual(stage["stage"], "post")
            self.assertEqual(stage["detail"], "review-final")

    def test_actions_carry_stage_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            actions = build_next_actions(root, gates={"brief": True, "style_locked": True})
            self.assertTrue(actions)
            for a in actions:
                self.assertIn("stage", a)
                self.assertIn("stage_label", a)
            write = next(a for a in actions if a["id"] == "write-spec")
            self.assertEqual(write["stage"], "agent")

    def test_persist_and_format_stage_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            stage = detect_pipeline_stage(
                root, gates={"brief": True, "style_locked": True, "spec": False}
            )
            line = format_stage_line(stage, compact=True)
            self.assertIn("片", line)
            paths = persist_pipeline_stage(
                root,
                stage,
                next_cmd="aifilm write-spec",
                next_id="write-spec",
                grok_home=Path(tmp) / "grokhome",
            )
            self.assertTrue(Path(paths["film"]).is_file())
            self.assertTrue(Path(paths["hud_txt"]).is_file())
            body = json.loads(Path(paths["film"]).read_text(encoding="utf-8"))
            self.assertEqual(body["stage"], "agent")
            self.assertIn("write-spec", body.get("next_id") or "")


class NextActionsSedimentOpt2Tests(unittest.TestCase):
    def test_tts_rehearse_when_clips_complete_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "receipts").mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "title": "x",
                        "tts_rehearsal_required": True,
                        "sound_plan": {"mood": "rnb"},
                    }
                ),
                encoding="utf-8",
            )
            actions = build_next_actions(
                root,
                gates={
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
            )
            ids = [a["id"] for a in actions]
            self.assertIn("tts-rehearse", ids)
            self.assertTrue(any("tts-rehearse" in a["cmd"] for a in actions))

    def test_fix_framing_when_lint_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "_framing_lint": {
                            "ok": False,
                            "codes": ["FRAMING_CROP_RISK"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            actions = build_next_actions(
                root,
                gates={"brief": True, "style_locked": True, "spec": True},
            )
            ids = [a["id"] for a in actions]
            self.assertIn("fix-framing", ids)


class PilotFailNotesTests(unittest.TestCase):
    def test_fail_writes_director_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            card = build_pilot_scorecard(
                shots=["shot01", "shot02"],
                scores={"identity": True, "style": False, "motion": True},
                reviewer="dex",
                notes="style drift",
            )
            write_pilot_scorecard(root, card)
            items = fail_scorecard_to_director_notes(root, card, enabled=True)
            self.assertEqual(len(items), 2)  # 2 shots × style fail
            notes = json.loads((root / "director_notes.json").read_text(encoding="utf-8"))
            open_items = [i for i in notes["items"] if i.get("status") == "open"]
            self.assertEqual(len(open_items), 2)
            self.assertTrue(all(i.get("reason_code") == "style" for i in open_items))


class PilotGateMessageTests(unittest.TestCase):
    def test_gate_message_mentions_pilot_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            with self.assertRaises(ProductionGateError) as ctx:
                assert_pilot_allows_add(
                    root,
                    shot_id="shot04",
                    existing_shot_ids={"shot01", "shot02", "shot03"},
                )
            msg = str(ctx.exception)
            self.assertIn("pilot report", msg)
            self.assertIn("pilot approve", msg)


if __name__ == "__main__":
    unittest.main()
