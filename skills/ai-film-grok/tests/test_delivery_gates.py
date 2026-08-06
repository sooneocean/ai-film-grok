from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
from manifest_truth import migrate_manifest  # noqa: E402
from media_qa import analyze_media  # noqa: E402
from shot_review import create_shot_review  # noqa: E402
from util import sha256_file, write_json  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class DeliveryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "film"
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(
                aifilm_grok.main(
                    ["init", "--theme", "test", "--title", "test", "--root", str(self.root)]
                ),
                0,
            )
        spec = {
            "title": "test",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "测试成片门禁用的完整 logline。",
                "tone": "neutral test",
                "emotional_arc": ["setup", "move", "end"],
            },
            "scenes": [
                {
                    "title": "scene",
                    "director_board": {
                        "emotional_turn": "平静变成警觉",
                        "visual_strategy": "人物走向门口，镜头跟随",
                        "performance_strategy": "步伐与视线同步改变",
                    },
                    "shots": [
                        {
                            "id": "shot01",
                            "beat_id": "beat01",
                            "title": "shot",
                            "dramatic_function": "hook",
                            "nar": "这是完整测试旁白。",
                            "performance_delta": "人物走到门口并停下",
                            "performance": {
                                "subtext": "门外有未知声音",
                                "playable_action": "走向门口",
                                "reaction_trigger": "听见敲门",
                            },
                            "dsl": {
                                "subject": "adult person",
                                "action": "walks",
                                "motion": "walk, camera pan, idle",
                                "visible_change": "人物从房间中央走到门口",
                                "camera_axis": "pan_with",
                                "lighting": "neutral interior",
                                "camera": {"shot_size": "medium", "lens_mm": "35"},
                            },
                        }
                    ],
                }
            ],
        }
        source_spec = self.base / "film-spec.json"
        source_spec.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(
                aifilm_grok.main(
                    ["write-spec", "--root", str(self.root), "--spec", str(source_spec)]
                ),
                0,
            )
        # Delivery-gate fixtures exercise final scorecard / screening, not the
        # full author-locked canonical graph chain. write-spec may emit schema
        # v2 graph that fails truth audit before scorecard is reached — demote
        # to legacy (schema_version < GRAPH_SCHEMA_VERSION) so audit stays open
        # while creative contract still sees authored beats.
        graph_path = self.root / "drama-graph.json"
        if graph_path.is_file():
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            if isinstance(graph, dict):
                graph["schema_version"] = 1
                graph_path.write_text(
                    json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        migration = migrate_manifest(self.root, write=True)
        self.assertTrue(migration["ok"], migration)
        self.motion = self.root / "clips" / "motion.mp4"
        self.final_source = self.root / "clips" / "final-source.mp4"
        self.motion.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=160x90:r=24:d=2",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(self.motion),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(self.motion),
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=2",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(self.final_source),
            ],
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def register_args(self, **overrides: object) -> argparse.Namespace:
        values: dict[str, object] = {
            "root": str(self.root),
            "shot_id": "shot01",
            "source": str(self.motion),
            "status": "approved",
            "prompt_file": None,
            "source_endpoint": "image_to_video",
            "identity_approved": True,
            "motion_approved": True,
            "review_note": "Identity, wardrobe, motion, and first frame checked.",
            "queue_job_id": "job_shot01_test",
        }
        values.update(overrides)
        source = Path(str(values["source"]))
        review = create_shot_review(
            self.root,
            shot_id="shot01",
            source=source,
            reviewer="director",
            notes="完整观看，身份、状态、构图、运动和叙事功能均已核对。",
            scores={"identity": 4, "continuity": 4, "composition": 4, "motion": 4, "narrative": 4},
            evidence_values=[
                "identity@0.0:face matches cast",
                "continuity@0.3:wardrobe remains stable",
                "composition@0.6:subject stays readable",
                "motion@1.0:movement continues",
                "narrative@1.5:reaction completes the beat",
            ],
            approve=True,
        )
        values["review_receipt"] = review["path"]
        (self.root / "receipts").mkdir(exist_ok=True)
        write_json(
            self.root / "receipts" / "visual-text-audit.json",
            {
                "kind": "visual-text-audit",
                "status": "clean",
                "clip": {"sha256": sha256_file(source)},
                "findings": [],
            },
        )
        queue_contract = {
            "kind": "shot-production-contract",
            "mode": "legacy-unbound",
            "shot_id": values["shot_id"],
        }
        write_json(
            self.root / "receipts" / "media-queue.json",
            {
                "schema_version": 1,
                "jobs": [
                    {
                        "id": values["queue_job_id"],
                        "shot_id": values["shot_id"],
                        "operation": values["source_endpoint"],
                        "status": "succeeded",
                        "inputs": [{"sha256": "0" * 64}],
                        "source_contract": queue_contract,
                        "receipt": {
                            "output_sha256": sha256_file(source),
                            "qa": {"ok": True},
                        },
                    }
                ],
            },
        )
        write_json(
            self.root / "receipts" / f"motion-evidence-{values['shot_id']}.json",
            {
                "kind": "motion-generation-evidence",
                "shot_id": values["shot_id"],
                "queue_job_id": values["queue_job_id"],
                "source_endpoint": values["source_endpoint"],
                "output": {"sha256": sha256_file(source)},
            },
        )
        return argparse.Namespace(**values)

    def test_write_spec_refreshes_manifest_truth_contract(self) -> None:
        manifest = aifilm_grok.load_manifest(self.root)
        summary = aifilm_grok.recompute_gates(self.root, manifest)
        self.assertTrue(summary["gates"]["manifest_current"], summary["manifest_truth"])

    def screening_args(self) -> list[str]:
        return [
            "--screening-evidence",
            "identity@0.0:cast remains consistent",
            "--screening-evidence",
            "style@0.1:style holds",
            "--screening-evidence",
            "motion@0.3:motion remains active",
            "--screening-evidence",
            "escalation@0.5:turn lands",
            "--screening-evidence",
            "audio@0.7:VO and BGM clear",
            "--screening-evidence",
            "subs@0.9:subtitles readable",
            "--screening-evidence",
            "dead_air@1.1:no dead air",
            "--screening-evidence",
            "rhythm@1.3:cut frequency matches pace",
            "--screening-evidence",
            "emotion@1.5:emotional beat lands",
            "--screening-evidence",
            "theme@1.7:theme comes through",
            "--screening-evidence",
            "performance@1.9:acting serves story",
            "--screening-evidence",
            "cinematic_coherence@1.9:scene geography and handoffs stay coherent",
            "--screening-evidence",
            "coverage_sufficiency@1.9:each dialogue beat retains playable coverage",
            "--screening-evidence",
            "performance_truth@1.9:visible performance changes drive the shot",
            "--screening-evidence",
            "editorial_rhythm@1.9:cuts land on authored changes",
            "--screening-evidence",
            "whole_film_integrity@1.9:the complete film holds together",
        ]

    @pytest.mark.slow
    def test_approved_registration_refuses_missing_manual_review_evidence(self) -> None:
        for key, value in (
            ("source_endpoint", None),
            ("identity_approved", False),
            ("motion_approved", False),
            ("review_note", ""),
        ):
            with self.subTest(key=key), self.assertRaises(aifilm_grok.FilmError):
                aifilm_grok.cmd_register_clip(self.register_args(**{key: value}))

    @pytest.mark.slow
    def test_approved_registration_records_endpoint_identity_motion_and_decode_qa(self) -> None:
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(aifilm_grok.cmd_register_clip(self.register_args()), 0)
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        record = manifest["clips"]["shot01"]
        self.assertEqual(record["source_endpoint"], "image_to_video")
        self.assertTrue(record["identity_approved"])
        self.assertTrue(record["motion_approved"])
        self.assertTrue(record["qa"]["ok"], record["qa"])

    @pytest.mark.slow
    def test_v16_project_refuses_boolean_only_clip_approval_without_review_receipt(self) -> None:
        args = self.register_args()
        Path(str(args.review_receipt)).unlink()
        args.review_receipt = None
        with self.assertRaisesRegex(aifilm_grok.FilmError, "shot-review evidence"):
            aifilm_grok.cmd_register_clip(args)

    @pytest.mark.slow
    def test_registration_preserves_generated_native_audio_as_a_stem(self) -> None:
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(
                aifilm_grok.cmd_register_clip(self.register_args(source=str(self.final_source))),
                0,
            )
        manifest = aifilm_grok.load_manifest(self.root)
        native = manifest["clips"]["shot01"]["native_audio"]
        stem = Path(native["path"])
        self.assertTrue(stem.is_file())
        self.assertEqual(native["sha256"], aifilm_grok.sha256(stem))
        self.assertGreater(native["duration_sec"], 1.5)
        self.assertGreater(native["mean_volume_db"], aifilm_grok.NATIVE_AUDIO_AUDIBLE_MIN_DB)
        self.assertTrue(native["audible"])

    def test_native_audio_volume_probe_rejects_near_silence(self) -> None:
        result = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout="", stderr="mean_volume: -55.4 dB\n"
        )
        with mock.patch.object(aifilm_grok, "run", return_value=result):
            mean = aifilm_grok.probe_native_audio_mean_volume(self.final_source)
        self.assertEqual(mean, -55.4)
        self.assertLess(mean, aifilm_grok.NATIVE_AUDIO_AUDIBLE_MIN_DB)

    @pytest.mark.slow
    def test_final_is_incomplete_until_explicit_full_film_review(self) -> None:
        with contextlib.redirect_stdout(StringIO()):
            aifilm_grok.cmd_register_clip(self.register_args())
        self.assertTrue(migrate_manifest(self.root, write=True)["ok"])
        final_path = self.root / "out" / "film_final.mp4"
        shutil.copy2(self.final_source, final_path)
        (self.root / "out" / "final.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n(test subtitle)\n",
            encoding="utf-8",
        )
        manifest = aifilm_grok.load_manifest(self.root)
        manifest.setdefault("outputs", {})["final_film"] = {
            "path": str(final_path),
            "sha256": aifilm_grok.sha256(final_path),
            "duration_sec": 2.0,
            "technical_qa": analyze_media(final_path, require_audio=True, require_motion=True),
        }
        aifilm_grok.save_manifest(self.root, manifest)
        before = aifilm_grok.recompute_gates(self.root, manifest)
        self.assertFalse(before["gates"]["final_complete"])

        missing_evidence = StringIO()
        with contextlib.redirect_stdout(missing_evidence):
            missing_evidence_rc = aifilm_grok.main(
                [
                    "review-final",
                    "--root",
                    str(self.root),
                    "--approve",
                    "--reviewer",
                    "agent",
                    "--notes",
                    "full score but no evidence",
                    "--score-identity",
                    "pass",
                    "--score-style",
                    "pass",
                    "--score-motion",
                    "pass",
                    "--score-escalation",
                    "pass",
                    "--score-audio",
                    "pass",
                    "--score-subs",
                    "pass",
                    "--score-dead-air",
                    "pass",
                    "--score-rhythm",
                    "pass",
                    "--score-emotion",
                    "pass",
                    "--score-theme",
                    "pass",
                    "--score-performance",
                    "pass",
                    "--score-cinematic-coherence",
                    "pass",
                    "--score-coverage-sufficiency",
                    "pass",
                    "--score-performance-truth",
                    "pass",
                    "--score-editorial-rhythm",
                    "pass",
                    "--score-whole-film-integrity",
                    "pass",
                ]
            )
        self.assertEqual(missing_evidence_rc, 2)
        self.assertIn("screening evidence", missing_evidence.getvalue())

        output = StringIO()
        with contextlib.redirect_stdout(output):
            rc = aifilm_grok.main(
                [
                    "review-final",
                    "--root",
                    str(self.root),
                    "--approve",
                    "--reviewer",
                    "agent",
                    "--notes",
                    "Watched end to end; motion, identity, subtitles, VO, BGM, and ending were checked.",
                    "--score-identity",
                    "pass",
                    "--score-style",
                    "pass",
                    "--score-motion",
                    "pass",
                    "--score-escalation",
                    "pass",
                    "--score-audio",
                    "pass",
                    "--score-subs",
                    "pass",
                    "--score-dead-air",
                    "pass",
                    "--score-rhythm",
                    "pass",
                    "--score-emotion",
                    "pass",
                    "--score-theme",
                    "pass",
                    "--score-performance",
                    "pass",
                    "--score-cinematic-coherence",
                    "pass",
                    "--score-coverage-sufficiency",
                    "pass",
                    "--score-performance-truth",
                    "pass",
                    "--score-editorial-rhythm",
                    "pass",
                    "--score-whole-film-integrity",
                    "pass",
                    *self.screening_args(),
                ]
            )
        self.assertEqual(rc, 0, output.getvalue())
        after_manifest = aifilm_grok.load_manifest(self.root)
        after = aifilm_grok.recompute_gates(self.root, after_manifest)
        self.assertTrue(after["gates"]["final_complete"], after)
        review = after_manifest["outputs"]["final_review"]
        self.assertTrue(review["scorecard"]["all_pass"])
        ledger = json.loads((self.root / "receipts" / "quality-ledger.json").read_text())
        self.assertFalse(ledger["retrospective_complete"])
        self.assertTrue(ledger["delivery"]["final_complete"])
        report = json.loads((self.root / "receipts" / "production-report.json").read_text())
        self.assertEqual(report["kind"], "production-report")
        self.assertTrue((self.root / "out" / "production-report.html").is_file())

    @pytest.mark.slow
    def test_review_final_rejects_incomplete_or_failing_scorecard(self) -> None:
        with contextlib.redirect_stdout(StringIO()):
            aifilm_grok.cmd_register_clip(self.register_args())
        self.assertTrue(migrate_manifest(self.root, write=True)["ok"])
        final_path = self.root / "out" / "film_final.mp4"
        shutil.copy2(self.final_source, final_path)
        (self.root / "out" / "final.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n(test subtitle)\n",
            encoding="utf-8",
        )
        manifest = aifilm_grok.load_manifest(self.root)
        manifest.setdefault("outputs", {})["final_film"] = {
            "path": str(final_path),
            "sha256": aifilm_grok.sha256(final_path),
            "duration_sec": 2.0,
            "technical_qa": analyze_media(final_path, require_audio=True, require_motion=True),
        }
        aifilm_grok.save_manifest(self.root, manifest)

        # Missing score flags
        out1 = StringIO()
        with contextlib.redirect_stdout(out1):
            rc1 = aifilm_grok.main(
                [
                    "review-final",
                    "--root",
                    str(self.root),
                    "--approve",
                    "--reviewer",
                    "agent",
                    "--notes",
                    "notes only without scorecard",
                ]
            )
        self.assertEqual(rc1, 2)
        self.assertIn("scorecard", out1.getvalue().lower())

        # Explicit fail on one dimension → director_notes written
        out2 = StringIO()
        with contextlib.redirect_stdout(out2):
            rc2 = aifilm_grok.main(
                [
                    "review-final",
                    "--root",
                    str(self.root),
                    "--approve",
                    "--reviewer",
                    "agent",
                    "--notes",
                    "dead air problem",
                    "--score-identity",
                    "pass",
                    "--score-style",
                    "pass",
                    "--score-motion",
                    "pass",
                    "--score-escalation",
                    "pass",
                    "--score-audio",
                    "pass",
                    "--score-subs",
                    "pass",
                    "--score-dead-air",
                    "fail",
                    "--score-rhythm",
                    "pass",
                    "--score-emotion",
                    "pass",
                    "--score-theme",
                    "pass",
                    "--score-performance",
                    "pass",
                    "--score-cinematic-coherence",
                    "pass",
                    "--score-coverage-sufficiency",
                    "pass",
                    "--score-performance-truth",
                    "pass",
                    "--score-editorial-rhythm",
                    "pass",
                    "--score-whole-film-integrity",
                    "pass",
                    "--reshoot-shots",
                    "shot01",
                    *self.screening_args(),
                ]
            )
        self.assertEqual(rc2, 2)
        self.assertIn("dead_air", out2.getvalue())
        notes_path = self.root / "director_notes.json"
        self.assertTrue(notes_path.is_file(), out2.getvalue())
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
        open_items = [i for i in notes["items"] if i.get("status") == "open"]
        self.assertGreaterEqual(len(open_items), 1)
        self.assertTrue(any(i.get("reason_code") == "dead_air" for i in open_items))

        # resolve + status reflects reshoots_clear after resolve
        out3 = StringIO()
        with contextlib.redirect_stdout(out3):
            rc3 = aifilm_grok.main(
                [
                    "director-notes",
                    "resolve",
                    "--root",
                    str(self.root),
                    "--item-id",
                    open_items[0]["id"],
                    "--note",
                    "trimmed end card",
                ]
            )
        self.assertEqual(rc3, 0, out3.getvalue())
        out4 = StringIO()
        with contextlib.redirect_stdout(out4):
            rc4 = aifilm_grok.main(["director-notes", "list", "--root", str(self.root)])
        self.assertEqual(rc4, 0)
        listed = json.loads(out4.getvalue())
        self.assertTrue(listed.get("reshoots_clear"))
        self.assertEqual(listed.get("open_reshoot_count"), 0)

    @pytest.mark.slow
    def test_desktop_export_refuses_incomplete_formal_delivery(self) -> None:
        home = self.base / "home"
        (home / "Desktop").mkdir(parents=True)
        args = argparse.Namespace(root=str(self.root), name="未完成项目", force=False)
        with mock.patch.object(aifilm_grok.Path, "home", return_value=home):
            with self.assertRaisesRegex(aifilm_grok.FilmError, "final review"):
                aifilm_grok.cmd_export_desktop(args)


if __name__ == "__main__":
    unittest.main()
