"""Tests for audio_plan.py — dry-run TTS/BGM/lipsync plan (no render).

Previously had ZERO test coverage. Tests cover:
  - build_audio_plan: missing spec, valid spec, recommendation generation
  - skill_dir: path resolution
  - TTS/BGM/lipsync probe integration (mocked)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_plan import build_audio_plan, skill_dir  # noqa: E402


class TestSkillDir(unittest.TestCase):
    """skill_dir returns the skill root path."""

    def test_returns_path(self):
        d = skill_dir()
        self.assertIsInstance(d, Path)
        # Should contain SKILL.md
        self.assertTrue((d / "SKILL.md").is_file())


class TestBuildAudioPlan(unittest.TestCase):
    """build_audio_plan builds a dry-run audio plan from film-spec."""

    def test_missing_spec(self):
        """Missing film-spec.json → ok=True but empty plan."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Mock all probes to avoid real deps
            with mock.patch.dict(sys.modules, {
                "tts_backend": mock.MagicMock(probe=lambda: {"ok": True, "active": "edge", "backends": {"edge": True}}),
                "sound_plan": mock.MagicMock(resolve_music_template=lambda *a, **kw: None),
                "lipsync_backend": mock.MagicMock(probe=lambda: {"ok": True, "ready": []}),
            }):
                plan = build_audio_plan(root)
            self.assertTrue(plan["ok"])
            self.assertEqual(plan["vo_mode"], "storyteller")

    def test_valid_spec_with_recommendations(self):
        """Spec with TTS config → recommendations generated."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "tts_backend": "edge",
                "vo_mode": "storyteller",
                "music_mood": "rnb",
                "shots": [{"id": "s1", "lipsync": True}],
                "scenes": [{"shots": [{"id": "s1", "lipsync": True}]}],
            }
            (root / "film-spec.json").write_text(json.dumps(spec))

            with mock.patch.dict(sys.modules, {
                "tts_backend": mock.MagicMock(probe=lambda: {
                    "ok": True, "active": "edge",
                    "backends": {"edge": True},
                    "voicebox_ok": False,
                }),
                "sound_plan": mock.MagicMock(resolve_music_template=lambda *a, **kw: None),
                "lipsync_backend": mock.MagicMock(probe=lambda: {"ok": True, "ready": []}),
                "audio_recipe": mock.MagicMock(
                    apply_audio_recipes_to_spec=lambda *a, **kw: {"counts": {"sfx": 3}},
                    probe_caps_for_root=lambda r: {"lipsync_ready": False, "music_library": False, "sung_provider_ready": False},
                ),
            }):
                plan = build_audio_plan(root)

            self.assertTrue(plan["ok"])
            self.assertEqual(plan["tts"]["film_spec_backend"], "edge")
            self.assertEqual(plan["music"]["mood"], "rnb")
            # lipsync target shots detected
            self.assertIn("s1", plan["lipsync"]["target_shots"])
            # recommendations present
            self.assertIsInstance(plan["recommendations"], list)
            self.assertTrue(len(plan["recommendations"]) > 0)

    def test_mood_from_sound_plan(self):
        """Mood is read from sound_plan.mood if present."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "sound_plan": {"mood": "dark"},
            }
            (root / "film-spec.json").write_text(json.dumps(spec))

            with mock.patch.dict(sys.modules, {
                "tts_backend": mock.MagicMock(probe=lambda: {"ok": True, "active": "edge", "backends": {"edge": True}}),
                "sound_plan": mock.MagicMock(resolve_music_template=lambda *a, **kw: None),
                "lipsync_backend": mock.MagicMock(probe=lambda: {"ok": True, "ready": []}),
            }):
                plan = build_audio_plan(root)
            self.assertEqual(plan["music"]["mood"], "dark")

    def test_tts_probe_error_handled(self):
        """TTS probe failure → graceful degradation."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def raise_err():
                raise RuntimeError("probe failed")

            with mock.patch.dict(sys.modules, {
                "tts_backend": mock.MagicMock(probe=raise_err),
                "sound_plan": mock.MagicMock(resolve_music_template=lambda *a, **kw: None),
                "lipsync_backend": mock.MagicMock(probe=lambda: {"ok": True, "ready": []}),
            }):
                plan = build_audio_plan(root)
            # Should not crash; plan still ok
            self.assertTrue(plan["ok"])


if __name__ == "__main__":
    unittest.main()
