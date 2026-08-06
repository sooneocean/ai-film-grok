import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_lib import cosine, extract_fingerprint, analyze_wav, sha256_file
from _wavutil import tmp_wav

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # so `from _wavutil import` resolves


class CosineTests(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(cosine([1, 0, 1], [1, 0, 1]), 1.0, places=6)

    def test_orthogonal(self):
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0, places=6)

    def test_empty(self):
        self.assertEqual(cosine([], []), 0.0)


class FingerprintTests(unittest.TestCase):
    def test_length_and_deterministic(self):
        p, _ = tmp_wav("fp.wav", dur=2.0)
        a = extract_fingerprint(p)
        b = extract_fingerprint(p)
        self.assertEqual(len(a), 101)
        self.assertEqual(a, b)
        # normalized to max 1.0
        self.assertAlmostEqual(max(a), 1.0, places=6)


class AnalyzeWavTests(unittest.TestCase):
    def test_metrics_on_sine(self):
        p, _ = tmp_wav("a.wav", dur=3.0, amp=24000, freq=220.0, sr=44100)
        m = analyze_wav(p)
        self.assertEqual(m["sample_rate"], 44100)
        self.assertEqual(m["channels"], 2)
        self.assertAlmostEqual(m["duration_sec"], 3.0, places=2)
        # peak ~24000/32767
        self.assertAlmostEqual(m["peak"], 24000 / 32767.0, places=2)
        self.assertGreater(m["rms"], 0.4)
        self.assertEqual(m["silence_ratio"], 0.0)

    def test_silent_file(self):
        p, _ = tmp_wav("s.wav", dur=1.0, amp=0)
        m = analyze_wav(p)
        self.assertEqual(m["peak"], 0.0)
        self.assertEqual(m["rms"], 0.0)


class ShaTests(unittest.TestCase):
    def test_stable(self):
        p, _ = tmp_wav("h.wav")
        self.assertEqual(sha256_file(p), sha256_file(p))
        self.assertEqual(len(sha256_file(p)), 64)


if __name__ == "__main__":
    unittest.main()
