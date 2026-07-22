from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from shot_review import ShotReviewError, approved_review_for_clip, create_shot_review  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class ShotReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clip = self.root / "motion.mp4"
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
                str(self.clip),
            ],
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _scores(self) -> dict[str, int]:
        return {"identity": 4, "continuity": 4, "composition": 5, "motion": 4, "narrative": 4}

    def _evidence(self) -> list[str]:
        return [
            "identity@0.0:face matches master",
            "continuity@0.6:wardrobe holds through movement",
            "composition@1.0:subject stays in vertical safe area",
            "motion@1.4:turn completes without freeze",
            "narrative@1.8:reaction lands before the cut",
        ]

    def _write_spec(self, channels: dict[str, object], **shot_fields: object) -> None:
        shot = {"id": "shot01", "content_channels": channels, **shot_fields}
        (self.root / "film-spec.json").write_text(
            json.dumps({"content_channels_strict": True, "scenes": [{"shots": [shot]}]}),
            encoding="utf-8",
        )

    def _review(self, *, performance: list[str] | None = None) -> dict[str, object]:
        return create_shot_review(
            self.root,
            shot_id="shot01",
            source=self.clip,
            reviewer="director",
            notes="完整观看，镜头完成信息变化。",
            scores=self._scores(),
            evidence_values=self._evidence(),
            performance_evidence_values=performance,
            approve=True,
        )

    @pytest.mark.slow
    def test_approved_review_creates_three_frames_contact_sheet_and_hash_binding(self) -> None:
        review = create_shot_review(
            self.root,
            shot_id="shot01",
            source=self.clip,
            reviewer="director",
            notes="完整观看，镜头完成信息变化。",
            scores=self._scores(),
            evidence_values=self._evidence(),
            approve=True,
        )
        self.assertTrue(review["approved"], review)
        self.assertTrue(Path(review["artifacts"]["contact_sheet"]["path"]).is_file())
        self.assertEqual(set(review["artifacts"]["frames"]), {"first", "middle", "last"})
        bound = approved_review_for_clip(self.root, shot_id="shot01", clip=self.clip)
        self.assertEqual(bound["path"], review["path"])

    @pytest.mark.slow
    def test_approval_rejects_missing_timestamp_evidence(self) -> None:
        with self.assertRaises(ShotReviewError):
            create_shot_review(
                self.root,
                shot_id="shot01",
                source=self.clip,
                reviewer="director",
                notes="evidence required",
                scores=self._scores(),
                evidence_values=["identity@0.0:only one"],
                approve=True,
            )

    @pytest.mark.slow
    def test_narration_on_camera_requires_mouth_still_human_evidence(self) -> None:
        self._write_spec({"voice": {"kind": "narration", "on_camera": True, "text": "旁白"}})
        with self.assertRaisesRegex(ShotReviewError, "performance evidence"):
            self._review()
        review = self._review(performance=["mouth_still@0.5:口型保持静止，旁白是画外声"])
        self.assertTrue(review["approved"])
        self.assertEqual(review["performance_contract"]["judgment_source"], "human_observation")
        self.assertTrue(
            Path(
                review["performance_contract"]["evidence"]["mouth_still"]["frame"]["path"]
            ).is_file()
        )

    @pytest.mark.slow
    def test_reaction_requires_visible_trigger_before_reaction(self) -> None:
        self._write_spec(
            {"performance": {"reaction_trigger": "手机亮起", "playable_action": "她后退一步"}}
        )
        with self.assertRaisesRegex(ShotReviewError, "REACTION_BEFORE_TRIGGER"):
            self._review(
                performance=[
                    "action_visible@0.7:后退完成",
                    "trigger_visible@1.0:手机亮起",
                    "reaction_visible@0.8:她收紧肩膀",
                ]
            )
        review = self._review(
            performance=[
                "action_visible@0.7:后退完成",
                "trigger_visible@0.4:手机亮起",
                "reaction_visible@0.8:她收紧肩膀",
            ]
        )
        self.assertTrue(review["approved"])

    @pytest.mark.slow
    def test_lipsync_dialogue_requires_delivery_evidence(self) -> None:
        self._write_spec(
            {"voice": {"kind": "dialogue", "text": "别走", "on_camera": True}}, lipsync=True
        )
        with self.assertRaisesRegex(ShotReviewError, "dialogue_delivery"):
            self._review()
        self.assertTrue(
            self._review(performance=["dialogue_delivery@0.6:嘴型与『别走』的发声同步"])["approved"]
        )

    @pytest.mark.slow
    def test_hash_mismatch_cannot_be_registered_from_another_clip(self) -> None:
        create_shot_review(
            self.root,
            shot_id="shot01",
            source=self.clip,
            reviewer="director",
            notes="reviewed",
            scores=self._scores(),
            evidence_values=self._evidence(),
            approve=True,
        )
        other = self.root / "other.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=160x90:r=24:d=2",
                "-vf",
                "hue=s=0",
                "-an",
                "-c:v",
                "libx264",
                str(other),
            ],
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(ShotReviewError, "hash"):
            approved_review_for_clip(self.root, shot_id="shot01", clip=other)
