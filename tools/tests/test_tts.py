import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tests dir for _wavutil
from tts import gap_asset_kind, choose_tts_engine, tts_qa
from _wavutil import tmp_wav


class AssetKindTests(unittest.TestCase):
    def test_default_bgm(self):
        self.assertEqual(gap_asset_kind({}), "bgm")
        self.assertEqual(gap_asset_kind({"asset_kind": "tts"}), "tts")


class TtsEngineTests(unittest.TestCase):
    def test_chooses_active_engine(self):
        eng = choose_tts_engine()
        self.assertIsNotNone(eng)
        eid, e = eng
        self.assertEqual(e.get("status"), "active")
        self.assertTrue(e.get("samples"))


class TtsQaTests(unittest.TestCase):
    def test_voice_qa_suppresses_loop(self):
        p, _ = tmp_wav("voice.wav", dur=3.0, amp=24000)
        r = tts_qa(p, {"duration": 3.0})
        self.assertTrue(r["ok"], msg=r["advisories"])
        # seamless-loop check must NOT fire for a spoken line
        self.assertFalse(any(a.startswith("loop_score") for a in r["advisories"]))
        # and the voice note must be present
        self.assertTrue(any("tts voice" in a for a in r["advisories"]))
        self.assertEqual(r["kind"], "tts")


if __name__ == "__main__":
    unittest.main()
