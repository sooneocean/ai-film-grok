"""Unit tests for the 4 Advanced Audio Engineering Optimizations:
1. Downbeat & Beat-Grid Quantization
2. Dynamic Spectral Ducking Filter Split
3. Cinematic Musical Stingers (sub_drop & reverse_cymbal)
4. Tempo-Pacing Lock (ASD to BPM mapping)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_sfx_bed import (  # noqa: E402
    build_bed,
    calculate_tempo_from_pacing,
    reverse_cymbal,
    sub_drop,
)
from sound_plan import quantize_timeline_to_beat  # noqa: E402


class AdvancedAudioOptimizationsTests(unittest.TestCase):
    def test_downbeat_quantization(self) -> None:
        raw_timeline = [
            {"start_sec": 0.0, "end_sec": 11.3, "mood": "ambient"},
            {"start_sec": 11.3, "end_sec": 24.8, "mood": "rnb"},
        ]
        # At 76 BPM, 1 beat ~ 0.789s, half-bar ~ 1.579s
        quantized = quantize_timeline_to_beat(raw_timeline, bpm=76.0)

        self.assertEqual(quantized[0]["start_sec"], 0.0)
        # 11.3s quantized to nearest 1.579s step is ~11.053s
        self.assertAlmostEqual(quantized[0]["end_sec"], quantized[1]["start_sec"])
        self.assertNotEqual(quantized[0]["end_sec"], 11.3)

    def test_sub_drop_and_reverse_cymbal_synthesis(self) -> None:
        sd = sub_drop(dur=1.0, amp=0.3)
        rc = reverse_cymbal(dur=1.0, amp=0.2)

        self.assertEqual(len(sd), 44100)
        self.assertEqual(len(rc), 44100)
        self.assertFalse(np.isnan(sd).any())
        self.assertFalse(np.isnan(rc).any())
        self.assertGreater(np.max(np.abs(sd)), 0.05)
        self.assertGreater(np.max(np.abs(rc)), 0.05)

    def test_calculate_tempo_from_pacing(self) -> None:
        # Fast cutting pacing: ASD = 2.0s -> 86.0 BPM
        fast_bpm = calculate_tempo_from_pacing([0, 2, 4, 6, 8], 10.0)
        self.assertEqual(fast_bpm, 86.0)

        # Slow cutting pacing: ASD = 8.0s -> 68.0 BPM
        slow_bpm = calculate_tempo_from_pacing([0, 8, 16], 24.0)
        self.assertEqual(slow_bpm, 68.0)

        # Medium pacing: ASD = 5.0s -> 76.0 BPM
        med_bpm = calculate_tempo_from_pacing([0, 5, 10], 15.0)
        self.assertEqual(med_bpm, 76.0)

    def test_stinger_auto_placement_in_build_bed(self) -> None:
        timeline = [
            {"start_sec": 0.0, "end_sec": 10.0, "mood": "dark"},
            {"start_sec": 10.0, "end_sec": 20.0, "mood": "rnb"},
        ]
        bed = build_bed(20.0, [0.0, 10.0], mood="rnb", mood_timeline=timeline, seed=42)

        self.assertEqual(bed.shape, (int(44100 * 20.0), 2))
        self.assertFalse(np.isnan(bed).any())
        # Check energy around transition (10.0s) has stinger hit
        trans_idx = int(10.0 * 44100)
        hit_energy = np.max(np.abs(bed[trans_idx : trans_idx + 4410]))
        self.assertGreater(hit_energy, 0.05)


if __name__ == "__main__":
    unittest.main()
