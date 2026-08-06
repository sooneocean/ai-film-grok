import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tests dir for _wavutil
from qa_audio import qa_asset, near_dup_advisory
from _wavutil import tmp_wav

REQ = {"duration": 3.0}


class HardGateTests(unittest.TestCase):
    def test_normal_passes(self):
        p, _ = tmp_wav("ok.wav", dur=3.0, amp=24000)
        r = qa_asset(p, {"duration": 3.0})
        self.assertTrue(r["ok"], msg=r["issues"])
        self.assertEqual(r["issues"], [])

    def test_clipping_fails(self):
        p, _ = tmp_wav("clip.wav", dur=3.0, amp=32767)
        r = qa_asset(p, {"duration": 3.0})
        self.assertFalse(r["ok"])
        self.assertTrue(any("peak" in i for i in r["issues"]))

    def test_quiet_fails(self):
        p, _ = tmp_wav("quiet.wav", dur=3.0, amp=100)
        r = qa_asset(p, {"duration": 3.0})
        self.assertFalse(r["ok"])

    def test_silent_fails(self):
        p, _ = tmp_wav("silent.wav", dur=2.0, amp=0)
        r = qa_asset(p, {"duration": 2.0})
        self.assertFalse(r["ok"])

    def test_short_fails(self):
        p, _ = tmp_wav("short.wav", dur=0.5, amp=24000)
        r = qa_asset(p, {"duration": 3.0})
        self.assertFalse(r["ok"])
        self.assertTrue(any("duration" in i for i in r["issues"]))

    def test_wrong_length_fails(self):
        p, _ = tmp_wav("wrong.wav", dur=5.0, amp=24000)
        r = qa_asset(p, {"duration": 30.0})
        self.assertFalse(r["ok"])


class AdvisoryTests(unittest.TestCase):
    def test_dc_advisory_nonblocking(self):
        p, _ = tmp_wav("dc.wav", dur=3.0, amp=24000, dc=400)
        r = qa_asset(p, {"duration": 3.0})
        # hard gates still pass -> ok True; dc flagged as advisory
        self.assertTrue(r["ok"])
        self.assertTrue(any("dc_offset" in a for a in r["advisories"]))

    def test_metrics_present(self):
        p, _ = tmp_wav("m.wav", dur=3.0, amp=24000)
        m = qa_asset(p, {"duration": 3.0})["metrics"]
        for k in ("peak", "rms", "silence_ratio", "duration_sec", "zcr",
                  "dc_offset", "lufs_est", "loop_score"):
            self.assertIn(k, m)


class NearDupTests(unittest.TestCase):
    def test_identical(self):
        fp = [0.5] * 101
        sim, aid = near_dup_advisory(fp, [("a", fp), ("b", [0.1] * 101)])
        self.assertAlmostEqual(sim, 1.0, places=6)
        self.assertEqual(aid, "a")

    def test_dissimilar(self):
        # anti-correlated alternating vectors -> cosine well below 0.5
        fp_a = [0.9 if i % 2 == 0 else 0.1 for i in range(101)]
        fp_b = [0.1 if i % 2 == 0 else 0.9 for i in range(101)]
        sim, _ = near_dup_advisory(fp_a, [("a", fp_b)])
        self.assertLess(sim, 0.5)  # caller applies the 0.98 threshold


if __name__ == "__main__":
    unittest.main()
