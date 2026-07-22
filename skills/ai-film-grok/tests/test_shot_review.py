from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=2", "-an", "-c:v", "libx264", str(self.clip)],
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
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=2", "-vf", "hue=s=0", "-an", "-c:v", "libx264", str(other)],
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(ShotReviewError, "hash"):
            approved_review_for_clip(self.root, shot_id="shot01", clip=other)
