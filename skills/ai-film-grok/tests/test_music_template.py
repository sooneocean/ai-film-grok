"""Phase H: local BGM template resolution."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from sound_plan import SoundPlanError, resolve_music_template  # noqa: E402


class MusicTemplateTests(unittest.TestCase):
    def test_auto_none_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audio").mkdir()
            self.assertIsNone(resolve_music_template(root, mood="rnb", mode="auto"))

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

    def test_on_fails_without_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audio").mkdir()
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


if __name__ == "__main__":
    unittest.main()
