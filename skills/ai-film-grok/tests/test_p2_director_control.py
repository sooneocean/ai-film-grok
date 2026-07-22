"""P2: per-join transitions, sound spotting, continuity lint — shipped paths."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import continuity  # noqa: E402
import edit_policy  # noqa: E402
import render_final  # noqa: E402
import sound_plan  # noqa: E402
from film_spec import FilmSpecError, validate_film_spec  # noqa: E402


def _moving_clip(path: Path, duration: float = 1.2) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=160x280:rate=30:duration={duration}",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _base_spec(n_shots: int = 3) -> dict:
    shots = []
    for i in range(n_shots):
        shots.append(
            {
                "id": f"shot{i + 1:02d}",
                "dramatic_function": ["hook", "approach", "afterglow"][min(i, 2)],
                "nar": f"旁白{i + 1}。",
                "dsl": {
                    "subject": "woman",
                    "cast": ["heroine"],
                    "camera": {"shot_size": "medium"},
                    "motion": "slow push-in, blink, idle not speaking",
                },
            }
        )
    return {
        "title": "p2",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "P2 控制面测试用完整 logline。",
            "tone": "test",
            "emotional_arc": ["a", "b", "c"],
        },
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": [{"shots": shots}],
    }


@pytest.mark.slow
class PerJoinTransitionTests(unittest.TestCase):
    @pytest.mark.slow
    def test_mixed_hard_soft_intents_resolve_different_use_ts(self) -> None:
        durs = [1.0, 2.0, 2.0, 2.0, 1.0]
        soft = edit_policy.segment_timeline(
            durs, 0.25, join_intents=["soft", "soft", "soft", "soft"]
        )
        mixed = edit_policy.segment_timeline(
            durs, 0.25, join_intents=["soft", "hard", "soft", "hold"]
        )
        self.assertTrue(mixed["enabled"])
        self.assertEqual(mixed["use_ts"][1], 0.0)  # hard
        self.assertGreater(mixed["use_ts"][0], 0.0)  # soft
        self.assertGreater(mixed["use_ts"][3], mixed["use_ts"][0] - 1e-9)  # hold ≥ soft
        # hard join does not shorten that step vs soft-only
        self.assertGreater(mixed["output_duration"], soft["output_duration"] - 0.01)

    @pytest.mark.slow
    def test_concat_videos_mixed_hard_soft_shortens_only_soft_joins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clips = []
            for i in range(3):
                p = root / f"c{i}.mp4"
                _moving_clip(p, 1.0)
                clips.append(p)
            out_soft = root / "soft.mp4"
            out_mixed = root / "mixed.mp4"
            plan_soft = render_final.concat_videos(
                clips, out_soft, transition_sec=0.25, join_intents=["soft", "soft"]
            )
            plan_mixed = render_final.concat_videos(
                clips, out_mixed, transition_sec=0.25, join_intents=["hard", "soft"]
            )
            self.assertTrue(plan_soft.get("enabled"))
            self.assertTrue(plan_mixed.get("enabled"))
            self.assertIn("hard", plan_mixed.get("join_methods") or [])
            self.assertIn("soft", plan_mixed.get("join_methods") or [])
            d_soft = render_final.pdur(out_soft)
            d_mixed = render_final.pdur(out_mixed)
            # hard first join → longer than all-soft
            self.assertGreater(d_mixed, d_soft + 0.05)
            # still shorter than pure hard sum 3.0
            self.assertLess(d_mixed, 2.95)

    @pytest.mark.slow
    def test_film_spec_rejects_wrong_intent_length(self) -> None:
        spec = _base_spec(3)
        spec["transition_intents"] = ["soft"]  # need 2
        with self.assertRaises(FilmSpecError):
            validate_film_spec(spec, assign_missing_ids=False)
        spec["transition_intents"] = ["soft", "hard"]
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(len(shots), 3)


@pytest.mark.slow
class SoundSpottingTests(unittest.TestCase):
    @pytest.mark.slow
    def test_expand_and_apply_mute(self) -> None:
        import numpy as np

        plan = sound_plan.validate_sound_plan(
            {
                "mood": "rnb",
                "bed": True,
                "events": [
                    {"type": "mute", "shot_id": "shot02", "duration_sec": 0.5},
                    {"type": "sfx_accent", "shot_id": "shot01", "kind": "heartbeat"},
                ],
            }
        )
        expanded = sound_plan.expand_sound_events(
            plan,
            shot_starts={"shot01": 1.0, "shot02": 5.0},
            total_duration=12.0,
        )
        self.assertEqual(expanded["event_count"], 2)
        mute = next(e for e in expanded["applied_events"] if e["type"] == "mute")
        self.assertAlmostEqual(mute["at_sec"], 5.0, places=2)
        sr = 1000
        samples = np.ones(12000, dtype=np.float64)
        out = sound_plan.apply_mute_windows_to_samples(
            samples, sr=sr, events=expanded["applied_events"]
        )
        a = int(5.0 * sr)
        b = int(5.5 * sr)
        self.assertTrue(np.allclose(out[a:b], 0.0))
        self.assertGreater(float(out[0]), 0.5)

    @pytest.mark.slow
    def test_invalid_event_type_rejected_in_film_spec(self) -> None:
        spec = _base_spec(2)
        spec["sound_plan"] = {"mood": "rnb", "events": [{"type": "explode"}]}
        with self.assertRaises(FilmSpecError):
            validate_film_spec(spec, assign_missing_ids=False)


@pytest.mark.slow
class ContinuityLintTests(unittest.TestCase):
    @pytest.mark.slow
    def test_cast_flip_and_clean_pair(self) -> None:
        bad = [
            {
                "id": "shot01",
                "dramatic_function": "hook",
                "dsl": {"cast": ["heroine"], "camera": {"shot_size": "medium"}},
            },
            {
                "id": "shot02",
                "dramatic_function": "approach",
                "dsl": {"cast": ["stranger"], "camera": {"shot_size": "medium"}},
            },
        ]
        report = continuity.lint_continuity(bad)
        self.assertFalse(report["ok"])
        self.assertIn(continuity.CODE_CAST_FLIP, report["codes"])

        clean = [
            {
                "id": "shot01",
                "dramatic_function": "hook",
                "dsl": {
                    "cast": ["heroine"],
                    "camera": {"shot_size": "medium"},
                    "screen_direction": "left",
                },
            },
            {
                "id": "shot02",
                "dramatic_function": "approach",
                "dsl": {
                    "cast": ["heroine"],
                    "camera": {"shot_size": "medium close-up"},
                    "screen_direction": "left",
                },
            },
        ]
        ok = continuity.lint_continuity(clean)
        self.assertTrue(ok["ok"])
        self.assertNotIn(continuity.CODE_CAST_FLIP, ok["codes"])

    @pytest.mark.slow
    def test_screen_direction_flip_code(self) -> None:
        shots = [
            {
                "id": "a",
                "dramatic_function": "hook",
                "dsl": {"cast": ["h"], "screen_direction": "left"},
            },
            {
                "id": "b",
                "dramatic_function": "action",
                "dsl": {"cast": ["h"], "screen_direction": "right"},
            },
        ]
        report = continuity.lint_continuity(shots)
        self.assertIn(continuity.CODE_SCREEN_DIRECTION_FLIP, report["codes"])
        self.assertFalse(report["ok"])

    @pytest.mark.slow
    def test_strict_continuity_on_film_spec(self) -> None:
        spec = _base_spec(2)
        spec["continuity_strict"] = True
        spec["scenes"][0]["shots"][0]["dsl"]["cast"] = ["heroine"]
        spec["scenes"][0]["shots"][1]["dsl"]["cast"] = ["other"]
        with self.assertRaisesRegex(FilmSpecError, "CAST_FLIP|continuity"):
            validate_film_spec(spec, assign_missing_ids=False)


if __name__ == "__main__":
    unittest.main()
