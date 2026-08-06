#!/usr/bin/env python3
"""Unit tests for the VIDEO lane (Grok Video 1.5 + local H3).

Pure-function / pure-tool tests that don't mutate the real repo:
  - qa_video hard-gate behavior (good passes; black / frozen clips fail)
  - validate_video_catalog contract (empty OK, good asset OK, bad rejected)
  - coverage_video analyze + priority_queue deficits
  - router.find_existing_video_candidate eligibility shortcut

End-to-end closed-loop (submit->poll->ingest->approve->fill) is covered by
tools/self_test.py on a throwaway repo copy (MockVideoBackend).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in os.sys.path:
    os.sys.path.insert(0, HERE)

from qa_video import qa_video
import validate_video_catalog as V
import coverage_video
from router import find_existing_video_candidate


def _ffmpeg():
    return shutil.which("ffmpeg")


def _make_clip(kind, path, dur=2):
    """Render a tiny test clip: kind in {good, black, frozen}."""
    ff = _ffmpeg()
    if not ff:
        raise unittest.SkipTest("ffmpeg not available; skipping video QA tests")
    if kind == "good":
        src = f"testsrc=size=320x240:rate=24:duration={dur}"
    elif kind == "black":
        src = f"color=c=black:s=320x240:r=24:d={dur}"
    else:  # frozen: single solid colour, no motion
        src = f"color=c=red:s=320x240:r=24:d={dur}"
    r = subprocess.run([ff, "-y", "-f", "lavfi", "-i", src, "-pix_fmt", "yuv420p",
                        path], capture_output=True, text=True)
    if r.returncode != 0:
        raise unittest.SkipTest(f"ffmpeg render failed: {r.stderr[-200:]}")


class TestQaVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="aifilm-vtest-")
        cls.good = os.path.join(cls.tmp, "good.mp4")
        cls.black = os.path.join(cls.tmp, "black.mp4")
        cls.frozen = os.path.join(cls.tmp, "frozen.mp4")
        _make_clip("good", cls.good)
        _make_clip("black", cls.black)
        _make_clip("frozen", cls.frozen)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_good_passes(self):
        res = qa_video(self.good, spec={"duration": 2.0, "resolution": "1080p"})
        self.assertTrue(res["ok"], f"good clip should pass: {res['issues']}")

    def test_black_fails(self):
        res = qa_video(self.black, spec={"duration": 2.0, "resolution": "1080p"})
        self.assertFalse(res["ok"])
        self.assertTrue(any("black" in i.lower() for i in res["issues"]),
                        f"expected black-frame issue, got {res['issues']}")

    def test_frozen_fails(self):
        res = qa_video(self.frozen, spec={"duration": 2.0, "resolution": "1080p"})
        self.assertFalse(res["ok"])
        self.assertTrue(any("frozen" in i.lower() or "static" in i.lower()
                            for i in res["issues"]),
                        f"expected frozen/static issue, got {res['issues']}")

    def test_duration_tolerance(self):
        # a 2s clip against a 12s request should fail the duration gate
        res = qa_video(self.good, spec={"duration": 12.0, "resolution": "1080p"})
        self.assertFalse(res["ok"])
        self.assertTrue(any("duration" in i.lower() for i in res["issues"]))


class TestValidateVideoCatalog(unittest.TestCase):
    def _reset(self):
        V.errors.clear()
        V.warnings.clear()

    def test_empty_library_warns_not_errors(self):
        self._reset()
        cat = {"schema": "aifilm-video-library-v1", "revision": 0,
               "updated_at": "2026-08-06T00:00:00+00:00", "assets": {}}
        # top-level checks only; empty assets -> warning, not error
        if cat.get("schema") != V.LIB_SCHEMA:
            V.err("schema")
        if not isinstance(cat.get("revision"), int):
            V.err("revision")
        if not V.is_iso(cat.get("updated_at", "")):
            V.err("updated_at")
        if not cat.get("assets"):
            V.warn("empty")
        self.assertEqual(V.errors, [])
        self.assertTrue(V.warnings)

    def test_good_asset_ok(self):
        self._reset()
        import tempfile
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "approved"), exist_ok=True)
        a = {
            "asset_id": "t2v-cinematic-abc12345",
            "schema": "aifilm-video-asset-v1",
            "status": "approved",
            "path": "approved/t2v-cinematic-abc12345.mp4",
            "sha256": "a" * 64,
            "model": "grok-video15",
            "seed": 1,
            "mode": "t2v",
            "source_image": None,
            "mood": "cinematic", "scene": "city", "style": "filmic",
            "energy": 0.5, "use_count": 0,
            "created_at": "2026-08-06T00:00:00+00:00",
            "recipe": {"recipe_id": "r1", "mode": "t2v", "mood": "cinematic",
                       "scene": "city", "style": "filmic", "energy": 0.5,
                       "resolution": "1080p", "duration": 12.0},
            "technical": {"ok": True, "errors": [], "advisories": [],
                          "codec": "h264", "width": 1920, "height": 1080,
                          "fps": 24.0, "duration_sec": 12.0,
                          "black_frame_ratio": 0.0, "frozen_score": 0.1,
                          "fingerprint": [0.1] * 64},
        }
        fname = a["path"].split("/")[-1]
        with open(os.path.join(root, "approved", fname), "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42")
        V.check_asset(a["asset_id"], a, root=root)
        self.assertEqual(V.errors, [], f"unexpected errors: {V.errors}")

    def test_bad_asset_rejected(self):
        self._reset()
        bad = {"asset_id": "x", "schema": "aifilm-video-asset-v1",
               "status": "bogus", "path": "x.wav", "sha256": "nope",
               "model": "", "seed": "x", "mode": "zzz", "source_image": 5,
               "mood": None, "scene": None, "style": None, "energy": 2,
               "use_count": -1, "created_at": "nope",
               "recipe": {}, "technical": {}}
        V.check_asset("x", bad, root="/tmp")
        self.assertTrue(V.errors, "expected multiple contract violations")


class TestCoverageVideo(unittest.TestCase):
    def test_starved_then_deficit(self):
        cat = {"schema": "aifilm-video-library-v1", "assets": {}}
        gaps = [
            {"action": "generate", "status": "open", "asset_kind": "video",
             "mood": "cinematic", "mode": "t2v", "energy": 0.5},
        ]
        a = coverage_video.analyze(cat, gaps, target_min=4)
        row = next(r for r in a["rows"]
                   if r["mood"] == "cinematic" and r["mode"] == "t2v")
        self.assertEqual(row["status"], "STARVED")
        prio = coverage_video.priority_queue(a, max_total=30)
        self.assertTrue(any(r["mood"] == "cinematic" and r["mode"] == "t2v"
                             for r, _ in prio))

    def test_approved_supply_counted(self):
        cat = {"schema": "aifilm-video-library-v1", "assets": {
            "t2v-cinematic-aa": {"status": "approved", "mood": "cinematic",
                                 "mode": "t2v", "energy": 0.5},
            "t2v-cinematic-bb": {"status": "approved", "mood": "cinematic",
                                 "mode": "t2v", "energy": 0.5},
        }}
        gaps = []
        a = coverage_video.analyze(cat, gaps, target_min=4)
        row = next(r for r in a["rows"]
                   if r["mood"] == "cinematic" and r["mode"] == "t2v")
        self.assertEqual(row["approved"], 2)
        self.assertEqual(row["effective"], 2)


class TestRouterVideo(unittest.TestCase):
    def test_existing_candidate_match(self):
        vcat = {"schema": "aifilm-video-library-v1", "assets": {
            "t2v-cinematic-aa": {"status": "approved", "mood": "cinematic",
                                 "mode": "t2v", "energy": 0.5, "scene": "city"},
        }}
        gap = {"action": "generate", "status": "open", "asset_kind": "video",
               "mood": "cinematic", "mode": "t2v", "energy": 0.52}
        self.assertEqual(find_existing_video_candidate(gap, vcat=vcat),
                         "t2v-cinematic-aa")

    def test_existing_candidate_mismatch_mode(self):
        vcat = {"schema": "aifilm-video-library-v1", "assets": {
            "t2v-cinematic-aa": {"status": "approved", "mood": "cinematic",
                                 "mode": "t2v", "energy": 0.5},
        }}
        gap = {"action": "generate", "status": "open", "asset_kind": "video",
               "mood": "cinematic", "mode": "i2v", "energy": 0.52}
        self.assertIsNone(find_existing_video_candidate(gap, vcat=vcat))

    def test_existing_candidate_only_approved(self):
        vcat = {"schema": "aifilm-video-library-v1", "assets": {
            "t2v-cinematic-aa": {"status": "pending_human_review", "mood": "cinematic",
                                 "mode": "t2v", "energy": 0.5},
        }}
        gap = {"action": "generate", "status": "open", "asset_kind": "video",
               "mood": "cinematic", "mode": "t2v", "energy": 0.52}
        self.assertIsNone(find_existing_video_candidate(gap, vcat=vcat))


if __name__ == "__main__":
    unittest.main()
