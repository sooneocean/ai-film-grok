import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tests dir for _wavutil
from router import capable_backends, choose_backend, find_existing_candidate, choose_route

GEN = {"schema": "aifilm-generators-v1", "backends": {
    "acestep": {"status": "active", "kind": "local", "asset_kind": ["bgm"],
                "capabilities": {"moods": ["ambient"], "stem_profiles": [], "max_duration": 120}},
    "ltx23": {"status": "active", "kind": "api", "asset_kind": ["bgm"],
              "capabilities": {"moods": ["ambient"], "stem_profiles": ["pad"], "max_duration": 60}},
    "grok15": {"status": "active", "kind": "api", "asset_kind": ["bgm"],
               "capabilities": {"moods": ["dramatic"], "stem_profiles": [], "max_duration": 90}},
    "fish": {"status": "archived_failed", "kind": "api",
             "capabilities": {"moods": ["ambient"], "stem_profiles": [], "max_duration": 60}},
}}


class CapableBackendsTests(unittest.TestCase):
    def test_skips_inactive(self):
        c = capable_backends({"mood": "ambient", "stem_profile": "pad", "duration": 30}, GEN)
        self.assertIn("acestep", c)
        self.assertIn("ltx23", c)
        self.assertNotIn("fish", c)  # archived_failed skipped

    def test_mood_filter(self):
        c = capable_backends({"mood": "dramatic", "stem_profile": None, "duration": 30}, GEN)
        self.assertIn("grok15", c)
        self.assertNotIn("acestep", c)
        self.assertNotIn("ltx23", c)

    def test_duration_filter(self):
        c = capable_backends({"mood": "ambient", "stem_profile": "pad", "duration": 90}, GEN)
        self.assertIn("acestep", c)
        self.assertNotIn("ltx23", c)  # max_duration 60 < 90

    def test_local_first(self):
        c = capable_backends({"mood": "ambient", "stem_profile": "pad", "duration": 30}, GEN)
        self.assertEqual(c[0], "acestep")  # local before api

    def test_exclude(self):
        c = capable_backends({"mood": "ambient", "stem_profile": "pad", "duration": 30},
                             GEN, exclude=("acestep",))
        self.assertEqual(c, ["ltx23"])

    def test_none_when_no_match(self):
        c = capable_backends({"mood": "xxx", "stem_profile": None, "duration": 30}, GEN)
        self.assertEqual(c, [])


class ChooseBackendTests(unittest.TestCase):
    def test_returns_first_capable(self):
        self.assertEqual(choose_backend({"mood": "ambient", "stem_profile": "pad", "duration": 30}, GEN), "acestep")

    def test_returns_none(self):
        self.assertIsNone(choose_backend({"mood": "zzz", "stem_profile": None, "duration": 30}, GEN))


class FindExistingCandidateTests(unittest.TestCase):
    def _catalog(self):
        return {"assets": {
            "amb-1": {"status": "approved", "mood": "ambient", "stem_profile": "pad",
                      "energy": 0.35, "technical": {"fingerprint": [0.1] * 101}},
            "amb-2": {"status": "pending_human_review", "mood": "ambient", "stem_profile": "pad",
                      "energy": 0.35, "technical": {"fingerprint": [0.1] * 101}},
        }}

    def test_match(self):
        gap = {"mood": "ambient", "stem_profile": "pad", "energy": 0.35}
        self.assertEqual(find_existing_candidate(gap, self._catalog()), "amb-1")

    def test_energy_mismatch(self):
        gap = {"mood": "ambient", "stem_profile": "pad", "energy": 0.6}
        self.assertIsNone(find_existing_candidate(gap, self._catalog()))

    def test_pending_not_eligible(self):
        gap = {"mood": "ambient", "stem_profile": "pad", "energy": 0.35}
        cat = self._catalog()
        cat["assets"]["amb-1"]["status"] = "pending_human_review"
        self.assertIsNone(find_existing_candidate(gap, cat))

    def test_mood_mismatch(self):
        gap = {"mood": "dramatic", "stem_profile": "pad", "energy": 0.35}
        self.assertIsNone(find_existing_candidate(gap, self._catalog()))


class ChooseRouteTests(unittest.TestCase):
    def test_bgm_route(self):
        gap = {"mood": "ambient", "stem_profile": "pad", "duration": 30}
        kind, target = choose_route(gap, GEN)
        self.assertEqual(kind, "bgm")
        self.assertIsNotNone(target)

    def test_tts_route(self):
        gap = {"asset_kind": "tts", "mood": "ambient", "stem_profile": "pad", "duration": 30}
        kind, _ = choose_route(gap, GEN)
        self.assertEqual(kind, "tts")


if __name__ == "__main__":
    unittest.main()
