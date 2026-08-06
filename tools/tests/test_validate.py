import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VAL = os.path.join(REPO, "tools", "validate_catalog.py")
PY = sys.executable


def _asset(path, energy=0.35):
    return {
        "schema": "aifilm-bgm-asset-v1",
        "asset_id": "amb-test",
        "status": "approved",
        "path": path,
        "sha256": "a" * 64,
        "model": "mock",
        "seed": 1,
        "recipe": {
            "recipe_id": "r", "mood": "ambient", "stem_profile": "pad",
            "dramatic_tags": [], "energy": energy, "keyscale": "C major",
            "timesignature": "4/4", "bpm": 72, "duration": 3.0,
        },
        "mood": "ambient", "dramatic_tags": [], "energy": energy,
        "stem_profile": "pad", "bpm": 72, "keyscale": "C major",
        "timesignature": "4/4", "motif_family": "", "series_id": "",
        "parent_asset_id": None, "instrumental": True,
        "technical": {
            "ok": True, "errors": [], "codec": "wav",
            "sample_rate": 44100, "channels": 2, "duration_sec": 3.0,
            "peak": 0.7, "rms": 0.5, "silence_ratio": 0.0,
            "fingerprint": [0.1] * 101,
        },
        "similarity_cluster": "amb-test", "use_count": 0,
        "created_at": "2026-08-05T00:00:00+00:00",
    }


def _write_catalog(d, assets, broken=False):
    cat = {"schema": "aifilm-bgm-library-v1", "revision": 1,
           "updated_at": "2026-08-05T00:00:00+00:00", "assets": assets}
    p = os.path.join(d, "catalog.json")
    json.dump(cat, open(p, "w"))
    return p


class ValidateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="aifilm-val-")
        # a real wav so the path-exists check passes
        wav = os.path.join(self.d, "amb-test.wav")
        import wave, struct, math
        with wave.open(wav, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
            fr = b"".join(struct.pack("<h", int(24000 * math.sin(2 * math.pi * 220 * i / 44100))) * 2
                          for i in range(44100 * 3))
            w.writeframes(fr)
        self.wav = "amb-test.wav"  # referenced relative to catalog dir

    def test_valid_passes(self):
        p = _write_catalog(self.d, {"amb-test": _asset(self.wav)})
        r = subprocess.run([PY, VAL, p, "--no-sha"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)

    def test_broken_energy_fails(self):
        p = _write_catalog(self.d, {"amb-test": _asset(self.wav, energy=2.0)})
        r = subprocess.run([PY, VAL, p, "--no-sha"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)

    def test_missing_field_fails(self):
        a = _asset(self.wav)
        del a["mood"]
        p = _write_catalog(self.d, {"amb-test": a})
        r = subprocess.run([PY, VAL, p, "--no-sha"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
