"""Procedural title sequence and end roll tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from export_composition import (  # noqa: E402
    derive_credits_from_spec,
    export_composition,
)


def _minimal_spec_with_cast(n_shots: int = 2, *, with_title_end: bool = False) -> dict:
    shots = []
    for i in range(1, n_shots + 1):
        shots.append(
            {
                "id": f"shot{i:02d}",
                "dramatic_function": "hook" if i == 1 else "reaction",
                "nar": f"话说第{i}镜。" if i == 1 else f"她轻轻眨眼，第{i}镜。",
                "duration_sec": 6,
                "lipsync": False,
                "dsl": {
                    "subject": "woman",
                    "action": "looks",
                    "motion": "slow push-in, soft blink, breathing, idle not speaking",
                },
            }
        )
    spec = {
        "title": "credits-test",
        "vo_mode": "storyteller",
        "transition_sec": 0.28,
        "director_intent": {
            "logline": "测试片头片尾精品化的完整一句话。",
            "tone": "测试",
            "emotional_arc": ["hook", "react", "end"],
            "cast": [
                {"name": "Alice", "role": "Heroine"},
                {"name": "Bob", "role": "Director"},
            ],
        },
        "scenes": [{"shots": shots}],
    }
    if with_title_end:
        spec["title_sequence"] = {
            "subtitle": "A Test Film",
            "tagline": "Procedural titles work",
            "show_motifs": True,
        }
        spec["end_roll"] = {
            "mode": "full",
            "cast_heading": "Cast",
            "crew_heading": "Crew",
            "show_shot_list": True,
            "scroll_duration_sec": 5,
        }
    return spec


def _seed_film_root(root: Path, *, n_shots: int = 2, with_title_end: bool = False) -> None:
    for name in ("clips", "out", "receipts", "keyframes", "prompts", "audio", "canonical"):
        (root / name).mkdir(parents=True, exist_ok=True)
    spec = _minimal_spec_with_cast(n_shots, with_title_end=with_title_end)
    (root / "film-spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    clips = {}
    for i in range(1, n_shots + 1):
        sid = f"shot{i:02d}"
        clip = root / "clips" / f"{sid}.mp4"
        clip.write_bytes(b"\x00\x00fake-mp4-placeholder")
        clips[sid] = {
            "shot_id": sid,
            "path": str(clip),
            "status": "approved",
            "duration_sec": 6.0,
            "source_endpoint": "image_to_video",
            "identity_approved": True,
            "motion_approved": True,
            "sha256": "abc",
        }
    manifest = {
        "schema_version": 1,
        "title": "credits-test",
        "width": 720,
        "height": 1280,
        "fps": 30,
        "clips": clips,
        "gates": {"clips_complete": True},
        "outputs": {},
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.slow
class DeriveCreditsTests(unittest.TestCase):
    @pytest.mark.slow
    def test_cast_from_director_intent(self) -> None:
        spec = {
            "title": "T",
            "director_intent": {
                "logline": "x",
                "tone": "y",
                "emotional_arc": ["a", "b", "c"],
                "cast": [
                    {"name": "Alice", "role": "Heroine"},
                    {"name": "Bob", "role": "Director"},
                ],
            },
            "scenes": [{"shots": [{"id": "s1", "title": "S1"}]}],
        }
        credits = derive_credits_from_spec(spec, {})
        self.assertEqual(credits["cast"][0]["name"], "Alice")
        self.assertEqual(credits["cast"][0]["role"], "Heroine")
        self.assertEqual(credits["cast"][1]["name"], "Bob")
        self.assertEqual(credits["crew"][0]["name"], "AI Film Grok")

    @pytest.mark.slow
    def test_fallback_cast_from_title(self) -> None:
        spec = {
            "title": "MyFilm",
            "director_intent": {
                "logline": "x",
                "tone": "y",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [{"shots": []}],
        }
        credits = derive_credits_from_spec(spec, {})
        self.assertEqual(len(credits["cast"]), 1)
        self.assertEqual(credits["cast"][0]["name"], "MyFilm")
        self.assertEqual(credits["cast"][0]["role"], "Director")

    @pytest.mark.slow
    def test_shots_extracted(self) -> None:
        spec = {
            "title": "T",
            "director_intent": {
                "logline": "x",
                "tone": "y",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {"shots": [{"id": "s1", "title": "First"}, {"id": "s2", "title": "Second"}]}
            ],
        }
        credits = derive_credits_from_spec(spec, {})
        self.assertEqual(len(credits["shots"]), 2)
        self.assertEqual(credits["shots"][0]["id"], "s1")
        self.assertEqual(credits["shots"][1]["title"], "Second")


@pytest.mark.slow
class TitleEndRollExportTests(unittest.TestCase):
    @pytest.mark.slow
    def test_spec_title_sequence_generates_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2, with_title_end=True)
            result = export_composition(
                root,
                engine="hyperframes",
                force=True,
            )
            self.assertTrue(result["ok"])
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="title-sequence"', html)
            self.assertIn('id="end-roll"', html)
            self.assertIn("A Test Film", html)
            self.assertIn("Alice", html)

    @pytest.mark.slow
    def test_title_sequence_none_suppresses_even_with_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2, with_title_end=True)
            result = export_composition(
                root,
                engine="hyperframes",
                force=True,
                title_sequence="none",
                end_roll="none",
            )
            self.assertTrue(result["ok"])
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('id="title-sequence"', html)
            self.assertNotIn('id="end-roll"', html)
            self.assertIn('id="title-card"', html)
            self.assertIn('id="end-card"', html)

    @pytest.mark.slow
    def test_end_roll_cast_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2, with_title_end=True)
            result = export_composition(
                root,
                engine="hyperframes",
                force=True,
                title_sequence="none",
                end_roll="cast_only",
            )
            self.assertTrue(result["ok"])
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="end-roll"', html)
            self.assertIn("Alice", html)
            self.assertNotIn('id="title-sequence"', html)

    @pytest.mark.slow
    def test_remotion_title_end_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2, with_title_end=True)
            result = export_composition(
                root,
                engine="remotion",
                force=True,
            )
            self.assertTrue(result["ok"])
            film_tsx = (root / "compose" / "remotion" / "src" / "Film.tsx").read_text(
                encoding="utf-8"
            )
            self.assertIn("TitleSequence", film_tsx)
            self.assertIn("EndRoll", film_tsx)

    @pytest.mark.slow
    def test_manifest_records_title_and_end_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2, with_title_end=True)
            export_composition(
                root,
                engine="hyperframes",
                force=True,
            )
            pkg = json.loads((root / "compose" / "package.json").read_text(encoding="utf-8"))
            self.assertTrue(pkg.get("title_sequence"))
            self.assertTrue(pkg.get("end_roll"))
            self.assertIn("credits", pkg)

    @pytest.mark.slow
    def test_backward_compat_old_spec_uses_minimal_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2, with_title_end=False)
            result = export_composition(
                root,
                engine="hyperframes",
                force=True,
            )
            self.assertTrue(result["ok"])
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="title-card"', html)
            self.assertIn('id="end-card"', html)
            self.assertNotIn('id="title-sequence"', html)
            self.assertNotIn('id="end-roll"', html)


if __name__ == "__main__":
    unittest.main()
