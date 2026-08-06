#!/usr/bin/env python3
"""Tests for the scene-assembly bridge (tools/assemble.py).

Pure-function tests (energy_bucket / match_bgm / auto_manifest) run in-process.
The ffmpeg end-to-end composite runs in an isolated subprocess with
AIFILM_BGM_LIB / AIFILM_VIDEO_LIB redirected to a throwaway library, so it can't
disturb the real repo or other tests.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in os.sys.path:
    os.sys.path.insert(0, HERE)

from assemble import energy_bucket, match_bgm, auto_manifest


class TestMatchBgm(unittest.TestCase):
    def _bgm(self, assets):
        return {"schema": "aifilm-bgm-library-v1", "revision": 0, "assets": assets}

    def test_same_mood_bucket_preferred(self):
        bgm = self._bgm({
            "ambient-pad-aa": {"asset_id": "ambient-pad-aa", "status": "approved",
                               "mood": "cinematic", "energy": 0.5},
            "ambient-pad-bb": {"asset_id": "ambient-pad-bb", "status": "approved",
                               "mood": "ambient", "energy": 0.5},
        })
        pick = match_bgm("cinematic", 0.5, bgm)
        self.assertEqual(pick["asset_id"], "ambient-pad-aa")

    def test_falls_back_to_bucket_then_energy(self):
        bgm = self._bgm({
            "ambient-pad-bb": {"asset_id": "ambient-pad-bb", "status": "approved",
                               "mood": "ambient", "energy": 0.2},
            "rnb-full-cc": {"asset_id": "rnb-full-cc", "status": "approved",
                            "mood": "cinematic", "energy": 0.9},
        })
        # no cinematic/low; should pick the cinematic one (closest energy)
        pick = match_bgm("cinematic", 0.1, bgm)
        self.assertEqual(pick["asset_id"], "rnb-full-cc")

    def test_skips_unapproved(self):
        bgm = self._bgm({
            "ambient-pad-aa": {"asset_id": "ambient-pad-aa", "status": "pending_human_review",
                               "mood": "cinematic", "energy": 0.5},
        })
        self.assertIsNone(match_bgm("cinematic", 0.5, bgm))


class TestAutoManifest(unittest.TestCase):
    def test_builds_segments_with_bgm(self):
        vcat = {"schema": "aifilm-video-library-v1", "assets": {
            "t2v-cinematic-aa": {"asset_id": "t2v-cinematic-aa", "status": "approved",
                                 "mood": "cinematic", "energy": 0.5, "path": "approved/v.mp4",
                                 "technical": {"duration_sec": 8.0}},
        }}
        bgm = {"schema": "aifilm-bgm-library-v1", "assets": {
            "ambient-pad-bb": {"asset_id": "ambient-pad-bb", "status": "approved",
                               "mood": "cinematic", "energy": 0.5},
        }}
        m = auto_manifest(1, film_id="f1", bgm_cat=bgm, vcat=vcat, tts_manifest={})
        self.assertEqual(m["film_id"], "f1")
        self.assertEqual(len(m["segments"]), 1)
        seg = m["segments"][0]
        self.assertEqual(seg["video_asset_id"], "t2v-cinematic-aa")
        self.assertEqual(seg["bgm_asset_id"], "ambient-pad-bb")
        self.assertEqual(seg["duration"], 8.0)
        # tts may be auto-selected from the real tts-evaluations manifest; the
        # important wiring is video + bgm, which we assert above.

    def test_no_video_raises(self):
        with self.assertRaises(RuntimeError):
            auto_manifest(1, vcat={"assets": {}}, bgm_cat={"assets": {}}, tts_manifest={})


class TestAssembleE2E(unittest.TestCase):
    def test_ffmpeg_composite(self):
        ff = shutil.which("ffmpeg")
        if not ff:
            raise unittest.SkipTest("ffmpeg unavailable; skipping assemble e2e")
        tmp = tempfile.mkdtemp(prefix="aifilm-assemble-test-")
        try:
            bgm_lib = os.path.join(tmp, "bgm-library")
            vid_lib = os.path.join(tmp, "video-library")
            for d in (bgm_lib, vid_lib):
                os.makedirs(os.path.join(d, "approved"), exist_ok=True)
            # bgm clip (sine) + catalog
            bgm_path = os.path.join(bgm_lib, "approved", "bgm.wav")
            subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                            bgm_path], capture_output=True)
            json.dump({"schema": "aifilm-bgm-library-v1", "revision": 1, "assets": {
                "ambient-pad-bb": {"status": "approved", "mood": "cinematic", "energy": 0.5,
                                   "path": "approved/bgm.wav"}}},
                open(os.path.join(bgm_lib, "catalog.json"), "w"), indent=2)
            # video clip (testsrc) + catalog
            vid_path = os.path.join(vid_lib, "approved", "vid.mp4")
            subprocess.run([ff, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2",
                            "-pix_fmt", "yuv420p", vid_path], capture_output=True)
            json.dump({"schema": "aifilm-video-library-v1", "revision": 1, "assets": {
                "t2v-cinematic-aa": {"status": "approved", "mood": "cinematic", "energy": 0.5,
                                     "path": "approved/vid.mp4",
                                     "technical": {"duration_sec": 2.0}}}},
                open(os.path.join(vid_lib, "catalog.json"), "w"), indent=2)
            out = os.path.join(tmp, "films", "out.mp4")
            env = dict(os.environ)
            env["AIFILM_BGM_LIB"] = bgm_lib
            env["AIFILM_VIDEO_LIB"] = vid_lib
            r = subprocess.run([os.sys.executable, os.path.join(HERE, "assemble.py"),
                                "--auto", "--segments", "1", "--film-id", "e2e",
                                "--out", out], cwd=HERE, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"assemble failed:\n{r.stdout}\n{r.stderr}")
            self.assertTrue(os.path.exists(out), "film output not created")
            # verify it's a decodable video with an audio track
            fp = shutil.which("ffprobe")
            if fp:
                info = subprocess.run([fp, "-v", "quiet", "-print_format", "json",
                                       "-show_streams", out], capture_output=True, text=True)
                d = json.loads(info.stdout)
                kinds = {s["codec_type"] for s in d.get("streams", [])}
                self.assertIn("video", kinds, "output missing video stream")
                self.assertIn("audio", kinds, "output missing mixed audio stream")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
