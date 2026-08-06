"""Sung-line provider abstraction — removes the HeartMuLa external-only gate."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
# sung_provider lives in the ``audio`` package; add it so the plain import works.
sys.path.insert(0, str(SCRIPTS / "audio"))


from audio_recipe import (  # noqa: E402
    probe_caps_for_root,
    resolve_shot_audio_recipe,
    validate_audio_policy,
)
from sung_provider import (  # noqa: E402
    HeartMuLaSungProvider,
    LocalFallbackSungProvider,
    SungProvider,
    select_sung_provider,
    sung_provider_ready,
)

pytestmark = pytest.mark.hotpath


def _env(**overrides: str):
    """Context manager forcing the sung-provider env to a known state.

    Empty string disables a var (``is_available`` checks ``.strip()``).
    """
    base = {
        "AIFILM_MUSIC_ARGV": "",
        "AIFILM_LOCAL_SUNG_PROVIDER": "",
        "AIFILM_MUSIC_REQUIRE": "",
    }
    base.update(overrides)
    return patch.dict(os.environ, base, clear=False)


class SungProviderContractTests(unittest.TestCase):
    def test_base_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            SungProvider()  # type: ignore[abstract]

    def test_concrete_subclass_instantiable(self) -> None:
        class Dummy(SungProvider):
            name = "dummy"
            kind = "local"

            def is_available(self) -> bool:
                return True

            def synthesize_beat(self, *, text, out_path, **kwargs):  # type: ignore[override]
                return {"path": str(out_path)}

        d = Dummy()
        self.assertTrue(d.is_available())
        self.assertEqual(d.kind, "local")


class HeartMuLaProviderTests(unittest.TestCase):
    def test_available_only_when_argv_set(self) -> None:
        with _env(AIFILM_MUSIC_ARGV=""):
            self.assertFalse(HeartMuLaSungProvider().is_available())
        with _env(AIFILM_MUSIC_ARGV='["python3","x.py"]'):
            self.assertTrue(HeartMuLaSungProvider().is_available())

    def test_synthesize_raises_without_config(self) -> None:
        with _env(AIFILM_MUSIC_ARGV=""):
            with self.assertRaises(Exception):
                HeartMuLaSungProvider().synthesize_beat(text="x", out_path=Path("/tmp/nope.wav"))


class LocalFallbackProviderTests(unittest.TestCase):
    def _fake_tts(self, text, out, voice=""):
        Path(out).write_text("fake-sung-stem")

    def test_available_when_injected(self) -> None:
        p = LocalFallbackSungProvider(tts_callable=self._fake_tts)
        self.assertTrue(p.is_available())

    def test_synthesize_writes_audio(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "sung.wav"
            p = LocalFallbackSungProvider(tts_callable=self._fake_tts)
            rcpt = p.synthesize_beat(text="la la", out_path=out, mood="rnb")
            self.assertTrue(out.is_file())
            self.assertEqual(rcpt["provider"], "local_fallback")
            self.assertFalse(rcpt["sung"])  # local TTS, not true singing
            self.assertIn("note", rcpt)

    def test_unavailable_without_env_or_adapter(self) -> None:
        # Force "no adapter detected" so this test validates the gate logic
        # rather than whatever local TTS happens to be installed here.
        with _env(AIFILM_LOCAL_SUNG_PROVIDER=""), patch(
            "sung_provider._detect_local_tts", return_value=None
        ):
            p = LocalFallbackSungProvider()
            self.assertFalse(p.is_available())

    def test_synthesize_raises_when_unavailable(self) -> None:
        with _env(AIFILM_LOCAL_SUNG_PROVIDER=""):
            p = LocalFallbackSungProvider()
            with self.assertRaises(Exception):
                p.synthesize_beat(text="x", out_path=Path("/tmp/nope.wav"))


class ProviderSelectionTests(unittest.TestCase):
    def test_external_preferred_when_configured(self) -> None:
        with _env(AIFILM_MUSIC_ARGV='["python3","x.py"]', AIFILM_LOCAL_SUNG_PROVIDER="1"):
            sel = select_sung_provider()
            self.assertIsInstance(sel, HeartMuLaSungProvider)

    def test_local_fallback_when_external_absent(self) -> None:
        with _env(AIFILM_MUSIC_ARGV="", AIFILM_LOCAL_SUNG_PROVIDER="1"):
            sel = select_sung_provider()
            self.assertIsInstance(sel, LocalFallbackSungProvider)

    def test_none_when_nothing_available(self) -> None:
        with _env(AIFILM_MUSIC_ARGV="", AIFILM_LOCAL_SUNG_PROVIDER=""), patch(
            "sung_provider._detect_local_tts", return_value=None
        ):
            self.assertIsNone(select_sung_provider())
            self.assertFalse(sung_provider_ready())


class RecipeUnblockTests(unittest.TestCase):
    def test_sung_beat_no_longer_blocked_by_heartmula(self) -> None:
        # With a local sung provider opted in, the probe reports ready without
        # any external HeartMuLa command.
        with _env(AIFILM_MUSIC_ARGV="", AIFILM_LOCAL_SUNG_PROVIDER="1"):
            caps = probe_caps_for_root(None)
            self.assertTrue(caps["sung_provider_ready"])

        shot = {
            "id": "s5",
            "dramatic_function": "action",
            "nar": "再近一点。",
            "camera": {"shot_size": "cu"},
            "audio_recipe": "sung_beat",
        }
        policy = validate_audio_policy({"mode": "musical_hybrid", "allow_sung": True})
        rec = resolve_shot_audio_recipe(
            shot,
            policy=policy,
            vo_mode="hybrid",
            index=4,
            n_shots=5,
            sung_slots_left=1,
            caps=caps,
        )
        self.assertEqual(rec["recipe"], "sung_beat")
        self.assertIsNone(rec.get("degraded_from"))


if __name__ == "__main__":
    unittest.main()
