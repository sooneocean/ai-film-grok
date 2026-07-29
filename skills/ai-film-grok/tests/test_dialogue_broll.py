from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_broll import (  # noqa: E402
    DialogueBrollError,
    default_dialogue_broll,
    validate_dialogue_broll,
    write_broll_edit_report,
)
from film_spec import FilmSpecError, validate_film_spec  # noqa: E402
from render_final import apply_dialogue_broll_visual, pdur  # noqa: E402


def _shot(duration: float = 8.0) -> dict:
    return {
        "id": "line01",
        "duration_sec": duration,
        "screen_mode": "on_camera",
        "dsl": {"motion": "locked close-up with breathing", "location_id": "train"},
    }


class TestDialogueBroll(unittest.TestCase):
    def test_long_dialogue_gets_one_safe_insert(self) -> None:
        shot = _shot()
        entries = default_dialogue_broll(shot)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["id"], "line01__broll01")
        self.assertEqual(entry["kind"], "insert")
        self.assertGreaterEqual(entry["start_sec"], 0.8)
        self.assertLessEqual(entry["end_sec"], 7.2)
        self.assertLessEqual(entry["end_sec"] - entry["start_sec"], 3.2)
        validate_dialogue_broll({**shot, "dialogue_broll": entries}, shot_id="line01")

    def test_short_dialogue_keeps_pure_a_roll(self) -> None:
        self.assertEqual(default_dialogue_broll(_shot(5.99)), [])

    def test_reaction_cover_uses_locked_listener_only_on_emotional_turn(self) -> None:
        shot = _shot()
        shot.update(
            {
                "speaker": "heroine",
                "dialogue": "The reveal leaves everyone stunned.",
                "performance_state": {"emotion": "shock"},
                "dsl": {"motion": "locked", "cast": ["heroine", "partner"]},
            }
        )
        entry = default_dialogue_broll(shot)[0]
        self.assertEqual(entry["kind"], "reaction")
        self.assertEqual(entry["dsl"]["cast"], ["partner"])
        validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_reaction_never_infers_a_listener_without_parent_speaker(self) -> None:
        shot = _shot()
        shot.update(
            {
                "dialogue": "The reveal leaves everyone stunned.",
                "performance_state": {"emotion": "shock"},
                "dsl": {"motion": "locked", "cast": ["heroine"]},
            }
        )
        self.assertNotEqual(default_dialogue_broll(shot)[0]["kind"], "reaction")

    def test_reaction_rejects_the_parent_speaker_as_listener(self) -> None:
        shot = _shot()
        shot["speaker"] = "heroine"
        entry = default_dialogue_broll(shot)[0]
        entry.update({"kind": "reaction", "shot_role": "hero"})
        entry["dsl"] = {"motion": "held reaction", "cast": ["heroine"]}
        with self.assertRaisesRegex(DialogueBrollError, "must not equal"):
            validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_environment_cover_and_adjacent_kind_do_not_repeat(self) -> None:
        shot = _shot()
        shot["dialogue"] = "Rain hits the station door outside."
        first = default_dialogue_broll(shot)[0]
        second = default_dialogue_broll(shot, previous_kind=first["kind"])[0]
        self.assertEqual(first["kind"], "env")
        self.assertNotEqual(second["kind"], first["kind"])

    def test_no_face_insert_is_enforced(self) -> None:
        shot = _shot()
        entry = default_dialogue_broll(shot)[0]
        entry["dsl"]["subject"] = "character face close-up"
        with self.assertRaisesRegex(DialogueBrollError, "no-face"):
            validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_no_face_insert_rejects_people_without_a_face_keyword(self) -> None:
        shot = _shot()
        entry = default_dialogue_broll(shot)[0]
        entry["dsl"]["subject"] = "a woman seen from behind in the rain"
        with self.assertRaisesRegex(DialogueBrollError, "no-face"):
            validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_reaction_requires_one_listener_and_no_lipsync(self) -> None:
        shot = _shot()
        shot["speaker"] = "heroine"
        entry = default_dialogue_broll(shot)[0]
        entry.update({"kind": "reaction", "shot_role": "hero"})
        entry["dsl"] = {"motion": "listener absorbs the reveal", "cast": ["passenger"]}
        validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")
        entry["lipsync"] = True
        with self.assertRaisesRegex(DialogueBrollError, "lipsync=false"):
            validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_cover_cannot_erase_more_than_forty_percent(self) -> None:
        shot = _shot()
        entry = default_dialogue_broll(shot)[0]
        entry["start_sec"], entry["end_sec"] = 0.8, 4.1
        with self.assertRaisesRegex(DialogueBrollError, "40%"):
            validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_cover_cannot_be_attached_to_silent_coverage(self) -> None:
        shot = _shot()
        shot["screen_mode"] = "reaction"
        with self.assertRaisesRegex(DialogueBrollError, "on_camera"):
            validate_dialogue_broll(
                {**shot, "dialogue_broll": default_dialogue_broll(_shot())}, shot_id="line01"
            )

    def test_non_finite_timing_is_rejected(self) -> None:
        shot = _shot()
        entry = default_dialogue_broll(shot)[0]
        entry["start_sec"] = float("nan")
        with self.assertRaisesRegex(DialogueBrollError, "finite"):
            validate_dialogue_broll({**shot, "dialogue_broll": [entry]}, shot_id="line01")

    def test_broll_is_rejected_outside_dialogue_drama(self) -> None:
        entry = default_dialogue_broll(_shot())[0]
        spec = {
            "title": "Legacy",
            "vo_mode": "storyteller",
            "director_intent": {"logline": "测试 B-roll 拒绝"},
            "scenes": [{"shots": [{**_shot(), "nar": "测试", "dialogue_broll": [entry]}]}],
        }
        with self.assertRaisesRegex(FilmSpecError, "dialogue_drama"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_edit_receipt_hash_binds_written_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report, path, digest = write_broll_edit_report(
                Path(tmp), [{"id": "line01__broll01", "actual_start_sec": 2.0}]
            )
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["entries"], report["entries"]
            )

    @unittest.skipUnless(__import__("shutil").which("ffmpeg"), "ffmpeg required")
    def test_visual_cutaway_preserves_parent_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent, cover = root / "parent.mp4", root / "cover.mp4"
            for path, color, duration in ((parent, "red", 8), (cover, "blue", 2)):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c={color}:s=160x284:r=24",
                        "-t",
                        str(duration),
                        "-an",
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            entry = default_dialogue_broll(_shot())[0]
            entry["clip"] = cover
            out, report = apply_dialogue_broll_visual(
                parent,
                parent_id="line01",
                parent_duration=8,
                entries=[entry],
                work=root,
                width=160,
                height=284,
                fps=24,
            )
            self.assertTrue(out.is_file())
            self.assertAlmostEqual(pdur(out), 8.0, delta=0.12)
            self.assertEqual(report[0]["audio_policy"], "carry_parent_dialogue")


if __name__ == "__main__":
    unittest.main()
