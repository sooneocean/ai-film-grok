#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from auto_cut import (  # noqa: E402
    PAD_AFTER_SEC,
    PAD_BEFORE_SEC,
    SILENCE_CLEAN_MS,
    AutoCutError,
    _segment_boundaries,
    _silence_gaps,
    build_edl,
    build_edl_for_root,
)
from real_footage import (  # noqa: E402
    RealFootageError,
    _source_id,
    footage_dirs,
    list_ingested,
    video_use_dir,
)
from util import write_json  # noqa: E402


def _make_transcript(words: list[tuple[float, float, str]]) -> dict:
    """Build a faster-whisper-shaped transcript from (start, end, text) tuples."""
    return {"segments": [{"words": [{"start": s, "end": e, "text": t} for (s, e, t) in words]}]}


class AutoCutTests(unittest.TestCase):
    def test_silence_gaps_detected(self) -> None:
        """DoD: silence gaps ≥150ms are detected; <150ms ignored."""
        words = [
            {"start": 0.0, "end": 1.0, "text": "hello"},
            {"start": 1.1, "end": 2.0, "text": "world"},  # 100ms gap (<150 → ignored)
            {"start": 2.6, "end": 3.5, "text": "again"},  # 600ms gap (≥400 → clean)
        ]
        gaps = _silence_gaps(words)
        self.assertEqual(len(gaps), 1)
        self.assertGreater(gaps[0][2], SILENCE_CLEAN_MS)

    def test_cuts_on_word_boundaries(self) -> None:
        """Hard Rule 6: every cut edge is a word boundary (never mid-word)."""
        words = [
            {"start": 0.0, "end": 1.0, "text": "a"},
            {"start": 1.5, "end": 2.5, "text": "b"},  # 500ms gap
            {"start": 3.0, "end": 4.0, "text": "c"},  # 500ms gap
        ]
        ranges = _segment_boundaries(words)
        self.assertTrue(len(ranges) >= 2)
        # Each range start is a valid word index
        for si, ei in ranges:
            self.assertGreaterEqual(si, 0)
            self.assertLessEqual(ei, len(words) - 1)

    def test_build_edl_pads_cut_edges(self) -> None:
        """Hard Rule 7: cut edges padded (30–200ms working window)."""
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp) / "t.json"
            write_json(
                tp,
                _make_transcript(
                    [
                        (0.0, 1.0, "first"),
                        (1.5, 2.5, "second"),  # 500ms gap
                        (3.0, 4.0, "third"),
                    ]
                ),
            )
            edl = build_edl(
                source_id="src1",
                source_path="/abs/src1.mp4",
                transcript_path=tp,
            )
            self.assertEqual(edl["version"], 1)
            self.assertEqual(edl["source_type"], "real_footage")
            self.assertTrue(edl["hard_rules"]["word_boundary_cuts"])
            self.assertEqual(edl["hard_rules"]["pad_before_sec"], PAD_BEFORE_SEC)
            self.assertEqual(edl["hard_rules"]["pad_after_sec"], PAD_AFTER_SEC)
            self.assertGreater(edl["total_duration_s"], 0)
            # First segment starts at 0 - pad_before (clamped to ≥0)
            self.assertGreaterEqual(edl["ranges"][0]["start"], 0.0)
            # Subtitles last flag set
            self.assertTrue(edl["hard_rules"]["subtitles_last"])

    def test_build_edl_max_segment_split(self) -> None:
        """Long monologue without gaps splits at max_segment_sec on ≥150ms gaps."""
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp) / "t.json"
            words = []
            t = 0.0
            for i in range(30):
                words.append((t, t + 0.8, f"w{i}"))
                t += 0.9  # 100ms gaps (<150) → forces max_segment split path
            write_json(tp, _make_transcript(words))
            edl = build_edl(
                source_id="src",
                source_path="/s.mp4",
                transcript_path=tp,
                max_segment_sec=3.0,
            )
            # With no clean gaps, segments still form; each ≤ ~3s + padding
            self.assertGreater(edl["segment_count"], 1)

    def test_build_edl_missing_transcript_raises(self) -> None:
        with self.assertRaises(AutoCutError):
            build_edl(
                source_id="x",
                source_path="/x.mp4",
                transcript_path=Path("/nonexistent/t.json"),
            )

    def test_build_edl_for_root_writes_receipt(self) -> None:
        """DoD: build_edl_for_root reads ingest receipt + writes edl.json."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dirs = footage_dirs(root)
            sid = "testsrc_abcd1234"
            # fake the transcript + ingest receipt
            write_json(
                dirs["transcripts"] / f"{sid}.json",
                _make_transcript([(0.0, 1.0, "hi"), (1.5, 2.0, "bye")]),
            )
            write_json(
                root / "receipts" / "footage-ingest" / f"{sid}.json",
                {
                    "source_id": sid,
                    "source_path": f"/abs/{sid}.mp4",
                },
            )
            edl = build_edl_for_root(root, sid)
            self.assertTrue(edl["path"].endswith("edl.json"))
            self.assertIn(sid, edl["sources"])

    def test_build_edl_for_root_missing_receipt_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AutoCutError):
                build_edl_for_root(Path(tmp), "nonexistent")


class RealFootageTests(unittest.TestCase):
    def test_footage_dirs_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dirs = footage_dirs(Path(tmp))
            self.assertTrue(dirs["raw"].is_dir())
            self.assertTrue(dirs["transcripts"].is_dir())
            self.assertTrue(dirs["edit"].is_dir())

    def test_source_id_is_stable(self) -> None:
        """source_id is deterministic from path stem + content hash."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "clip.mp4"
            src.write_bytes(b"hello footage")
            sid1 = _source_id(src)
            sid2 = _source_id(src)
            self.assertEqual(sid1, sid2)
            self.assertIn("clip", sid1)

    def test_list_ingested_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_ingested(Path(tmp)), [])

    def test_video_use_missing_raises(self) -> None:
        """When video-use not resolvable, ingest raises a clear error."""
        # This test assumes the real video-use skill is NOT installed in CI;
        # if it is, ingest would need a real video — skip instead.
        try:
            video_use_dir()
            self.skipTest("video-use present — ingest needs real footage")
        except RealFootageError:
            pass


if __name__ == "__main__":
    unittest.main()
