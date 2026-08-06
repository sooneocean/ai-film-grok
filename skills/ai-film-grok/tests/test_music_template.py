"""Phase H: local BGM template resolution."""

from __future__ import annotations

import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sound_plan  # noqa: E402
from render_final import SR, render_music_template_timeline  # noqa: E402
from sound_plan import (  # noqa: E402
    SoundPlanError,
    resolve_music_template,
    resolve_music_template_timeline,
)


class MusicTemplateTests(unittest.TestCase):
    def test_auto_defers_to_procedural_bgm_when_shared_library_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audio").mkdir()
            with mock.patch.object(
                sound_plan, "__file__", str(root / "isolated" / "sound_plan.py")
            ):
                hit = resolve_music_template(root, mood="rnb", mode="auto")
            self.assertIsNone(hit)

    def test_auto_picks_bgm_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio"
            audio.mkdir()
            bgm = audio / "bgm.wav"
            bgm.write_bytes(b"\x00" * 200)
            hit = resolve_music_template(root, mood="rnb", mode="auto")
            assert hit is not None
            self.assertEqual(hit["source"], "local_template")
            self.assertTrue(Path(hit["path"]).is_file())
            self.assertIn("bgm.wav", hit.get("relative") or hit["path"])

    def test_mood_template_rnb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = root / "audio" / "templates"
            tdir.mkdir(parents=True)
            (tdir / "rnb.wav").write_bytes(b"\x00" * 200)
            hit = resolve_music_template(root, mood="sensual", mode="auto")
            assert hit is not None
            self.assertIn("rnb.wav", hit["path"])

    def test_on_requires_an_explicit_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audio").mkdir()
            with mock.patch.object(
                sound_plan, "__file__", str(root / "isolated" / "sound_plan.py")
            ):
                with self.assertRaises(SoundPlanError):
                    resolve_music_template(root, mood="rnb", mode="on")

    def test_cli_music_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio"
            audio.mkdir()
            (audio / "bgm.wav").write_bytes(b"\x00" * 200)
            explicit = root / "custom.mp3"
            explicit.write_bytes(b"\x00" * 200)
            hit = resolve_music_template(
                root,
                mood="rnb",
                mode="auto",
                music_arg=str(explicit),
                music_license="My License",
            )
            assert hit is not None
            self.assertEqual(hit["source"], "cli_music")
            self.assertEqual(hit["license_note"], "My License")

    def test_license_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio"
            audio.mkdir()
            bgm = audio / "bgm.wav"
            bgm.write_bytes(b"\x00" * 200)
            (audio / "bgm.license.txt").write_text("Epidemic personal use\n", encoding="utf-8")
            hit = resolve_music_template(root, mood="rnb", mode="auto")
            assert hit is not None
            self.assertIn("Epidemic", hit["license_note"])

    def test_off_ignores_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio"
            audio.mkdir()
            (audio / "bgm.wav").write_bytes(b"\x00" * 200)
            self.assertIsNone(resolve_music_template(root, mood="rnb", mode="off"))

    def test_pool_rotates_by_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = root / "audio" / "templates" / "rnb"
            tdir.mkdir(parents=True)
            a = tdir / "a.wav"
            b = tdir / "b.wav"
            a.write_bytes(b"\x00" * 200)
            b.write_bytes(b"\x01" * 200)
            hit0 = resolve_music_template(root, mood="rnb", mode="auto", seed=0)
            hit1 = resolve_music_template(root, mood="rnb", mode="auto", seed=1)
            assert hit0 is not None and hit1 is not None
            self.assertEqual(hit0["pool_size"], 2)
            self.assertEqual(hit1["pool_size"], 2)
            # different seeds → different pool slots when size=2
            self.assertNotEqual(hit0["path"], hit1["path"])
            self.assertEqual(hit0["pool_index"], 0)
            self.assertEqual(hit1["pool_index"], 1)

    def test_timeline_selects_by_mood_and_ignores_global_bgm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio"
            (audio / "templates" / "rnb").mkdir(parents=True)
            (audio / "templates" / "dark").mkdir(parents=True)
            (audio / "bgm.wav").write_bytes(b"global" * 100)
            (audio / "templates" / "rnb" / "velvet.wav").write_bytes(b"rnb" * 100)
            (audio / "templates" / "dark" / "pulse.wav").write_bytes(b"dark" * 100)
            (audio / "templates" / "rnb" / "velvet.license.txt").write_text(
                "test", encoding="utf-8"
            )
            (audio / "templates" / "dark" / "pulse.license.txt").write_text(
                "test", encoding="utf-8"
            )
            routed = resolve_music_template_timeline(
                root,
                seed=9,
                timeline=[
                    {
                        "shot_id": "s1",
                        "mood": "rnb",
                        "motif_id": "hook",
                        "start_sec": 0,
                        "end_sec": 2,
                    },
                    {
                        "shot_id": "s2",
                        "mood": "dark",
                        "motif_id": "threat",
                        "start_sec": 2,
                        "end_sec": 4,
                    },
                ],
            )
            self.assertEqual([item["shot_id"] for item in routed], ["s1", "s2"])
            self.assertIn("velvet.wav", routed[0]["path"])
            self.assertIn("pulse.wav", routed[1]["path"])
            self.assertNotIn("bgm.wav", " ".join(item["path"] for item in routed))

    def test_timeline_does_not_substitute_default_for_missing_mood(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = root / "audio" / "templates"
            tdir.mkdir(parents=True)
            (tdir / "default.wav").write_bytes(b"default" * 100)
            routed = resolve_music_template_timeline(
                root,
                timeline=[{"shot_id": "s1", "mood": "warm", "start_sec": 0, "end_sec": 2}],
            )
            self.assertEqual(routed, [])

    def test_timeline_rejects_template_without_license(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "audio" / "templates" / "rnb" / "unlicensed.wav"
            template.parent.mkdir(parents=True)
            template.write_bytes(b"unlicensed" * 100)
            with self.assertRaisesRegex(SoundPlanError, "requires a license sidecar"):
                resolve_music_template_timeline(
                    root,
                    timeline=[{"shot_id": "s1", "mood": "rnb", "start_sec": 0, "end_sec": 2}],
                )

    def test_timeline_renders_different_template_sources_per_cue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rnb = root / "audio" / "templates" / "rnb" / "a.wav"
            dark = root / "audio" / "templates" / "dark" / "b.wav"
            for path, level in ((rnb, 0.2), (dark, -0.2)):
                path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(path), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(SR)
                    handle.writeframes((np.full(SR, level * 32767)).astype(np.int16).tobytes())
                path.with_suffix(".license.txt").write_text("test", encoding="utf-8")
            bed, selections = render_music_template_timeline(
                root=root,
                work=root / "work",
                seed=4,
                total_dur=4,
                plan={},
                music_license="test",
                timeline=[
                    {
                        "shot_id": "s1",
                        "mood": "rnb",
                        "motif_id": "hook",
                        "start_sec": 0,
                        "end_sec": 2,
                        "transition": "crossfade",
                    },
                    {
                        "shot_id": "s2",
                        "mood": "dark",
                        "motif_id": "threat",
                        "start_sec": 2,
                        "end_sec": 4,
                        "transition": "cut",
                    },
                ],
            )
            self.assertEqual([item["shot_id"] for item in selections], ["s1", "s2"])
            self.assertGreater(float(bed[: SR // 2].mean()), 0.0)
            self.assertLess(float(bed[3 * SR : 3 * SR + SR // 2].mean()), 0.0)

    def test_skill_library_receipt_path_is_not_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "assets" / "bgm" / "rnb"
            library.mkdir(parents=True)
            (library / "bed.wav").write_bytes(b"shared" * 100)
            (library / "bed.license.txt").write_text("test", encoding="utf-8")
            with mock.patch.object(
                sound_plan, "__file__", str(root / "shared" / "scripts" / "sound_plan.py")
            ):
                routed = resolve_music_template_timeline(
                    root,
                    timeline=[{"shot_id": "s1", "mood": "rnb", "start_sec": 0, "end_sec": 2}],
                )
            self.assertEqual(routed[0]["relative"], "skill_library/rnb/bed.wav")


if __name__ == "__main__":
    unittest.main()
