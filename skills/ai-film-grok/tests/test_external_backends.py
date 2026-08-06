from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lipsync_backend  # noqa: E402
import tts_backend  # noqa: E402


class ExternalLipSyncTests(unittest.TestCase):
    """v2.40: external lipsync argv path removed — only frozen probe/raise remains."""

    def test_legacy_shell_template_is_rejected(self) -> None:
        with self.assertRaises(lipsync_backend.LipSyncError):
            lipsync_backend.lipsync_one(
                video="/tmp/a.mp4", audio="/tmp/a.wav", out="/tmp/o.mp4", backend="external"
            )

    def test_external_backend_executes_structured_argv_without_shell(self) -> None:
        probe = lipsync_backend.probe()
        self.assertTrue(probe.get("frozen"))
        self.assertEqual(probe.get("ready"), [])
        with self.assertRaises(lipsync_backend.LipSyncError):
            lipsync_backend.enforce_dialogue_lipsync(
                vo_mode="hybrid", shots=[], requested="external"
            )

@pytest.mark.slow
class ExternalTTSTests(unittest.TestCase):
    @pytest.mark.slow
    def test_legacy_shell_template_is_rejected(self) -> None:
        with (
            mock.patch.dict(
                os.environ,
                {"AIFILM_TTS_CMD": "python tool.py --text_file {text_file} --out {out}"},
                clear=True,
            ),
            self.assertRaises(tts_backend.TTSError),
        ):
            tts_backend.external_argv()

    @pytest.mark.slow
    def test_external_backend_executes_structured_argv_without_shell(self) -> None:
        raw = json.dumps(
            [
                "python3",
                "/opt/tts.py",
                "--text-file",
                "{text_file}",
                "--out",
                "{out}",
                "--voice",
                "{voice}",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "voice; touch PWNED.mp3"

            def completed(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                out.write_bytes(b"result")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with mock.patch.dict(os.environ, {"AIFILM_TTS_ARGV": raw}, clear=True):
                with mock.patch.object(tts_backend.subprocess, "run", side_effect=completed) as run:
                    tts_backend.tts_external("你好; $(touch PWNED)", out, voice="voice;id")

            argv = run.call_args.args[0]
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[5], str(out))
            self.assertEqual(argv[7], "voice;id")
            self.assertFalse(run.call_args.kwargs.get("shell", False))
            self.assertEqual(run.call_args.kwargs["timeout"], 300)
            self.assertNotIn("FISH_API_KEY", run.call_args.kwargs["env"])

    @pytest.mark.slow
    def test_explicit_external_failure_does_not_send_text_to_edge(self) -> None:
        info = {"active": "external", "backends": {"external": True, "edge": True}}
        with (
            mock.patch.object(tts_backend, "probe", return_value=info),
            mock.patch.object(
                tts_backend, "tts_external", side_effect=tts_backend.TTSError("local failed")
            ),
            mock.patch.object(tts_backend, "tts_edge") as edge,
            tempfile.TemporaryDirectory() as tmp,
        ):
            with self.assertRaises(tts_backend.TTSError):
                tts_backend.synthesize(
                    "private script text",
                    Path(tmp) / "out.mp3",
                    backend="external",
                )
        edge.assert_not_called()

    @pytest.mark.slow
    def test_unknown_backend_fails_closed(self) -> None:
        info = {"active": "edge", "backends": {"edge": True}}
        with mock.patch.object(tts_backend, "probe", return_value=info):
            with mock.patch.object(tts_backend, "tts_edge") as edge:
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(tts_backend.TTSError):
                        tts_backend.synthesize("private", Path(tmp) / "out.mp3", backend="mystery")
        edge.assert_not_called()

    @pytest.mark.slow
    def test_voicebox_backend_calls_adapter(self) -> None:
        info = {
            "active": "voicebox",
            "backends": {"voicebox": True, "edge": True},
            "voicebox_profile": "storyteller",
            "voicebox_profile_id": "pid-1",
        }

        def fake_vb(text: str, out: Path, **_: object) -> Path:
            out.write_bytes(b"RIFF" + b"\x00" * 100 + b"WAVE" + b"\x00" * 200)
            return out

        with mock.patch.object(tts_backend, "probe", return_value=info):
            with mock.patch.object(tts_backend, "tts_voicebox", side_effect=fake_vb) as vb:
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / "out.mp3"
                    meta = tts_backend.synthesize(
                        "话说那天夜里",
                        out,
                        backend="voicebox",
                        voice="storyteller",
                    )
        vb.assert_called_once()
        self.assertIn("voicebox", meta["backend"])
        self.assertEqual(meta["voice"], "storyteller")

    @pytest.mark.slow
    def test_explicit_edge_failure_does_not_use_voicebox_without_opt_in(self) -> None:
        info = {
            "active": "edge",
            "backends": {"edge": True, "voicebox": True},
            "voicebox_profile": "storyteller",
        }
        with mock.patch.dict(os.environ, {"AIFILM_TTS_VOICEBOX_FALLBACK": "0"}, clear=False):
            with mock.patch.object(tts_backend, "probe", return_value=info):
                with mock.patch.object(
                    tts_backend, "tts_edge", side_effect=tts_backend.TTSError("edge down")
                ):
                    with mock.patch.object(tts_backend, "tts_voicebox") as vb:
                        with tempfile.TemporaryDirectory() as tmp:
                            with self.assertRaises(tts_backend.TTSError):
                                tts_backend.synthesize(
                                    "private",
                                    Path(tmp) / "out.mp3",
                                    backend="edge",
                                    voice="zh-CN-YunxiNeural",
                                )
        vb.assert_not_called()

    @pytest.mark.slow
    def test_voicebox_fallback_opt_in_on_edge_failure(self) -> None:
        info = {
            "active": "edge",
            "backends": {"edge": True, "voicebox": True},
            "voicebox_profile": "storyteller",
            "voicebox_profile_id": "pid-1",
        }

        def fake_vb(text: str, out: Path, **_: object) -> Path:
            out.write_bytes(b"RIFF" + b"\x00" * 100 + b"WAVE" + b"\x00" * 200)
            return out

        with mock.patch.dict(os.environ, {"AIFILM_TTS_VOICEBOX_FALLBACK": "1"}, clear=False):
            with mock.patch.object(tts_backend, "probe", return_value=info):
                with mock.patch.object(
                    tts_backend, "tts_edge", side_effect=tts_backend.TTSError("edge down")
                ):
                    with mock.patch.object(tts_backend, "tts_voicebox", side_effect=fake_vb) as vb:
                        with tempfile.TemporaryDirectory() as tmp:
                            meta = tts_backend.synthesize(
                                "private",
                                Path(tmp) / "out.mp3",
                                backend="edge",
                                voice="zh-CN-YunxiNeural",
                            )
        vb.assert_called_once()
        self.assertEqual(meta["backend"], "edge->voicebox_opt_in_fallback")

    @pytest.mark.slow
    def test_auto_fallback_prefers_voicebox_then_edge(self) -> None:
        info = {
            "active": "minimax",
            "backends": {"minimax": True, "voicebox": True, "edge": True},
            "voicebox_profile": "storyteller",
        }

        def fake_vb(text: str, out: Path, **_: object) -> Path:
            out.write_bytes(b"RIFF" + b"\x00" * 100 + b"WAVE" + b"\x00" * 200)
            return out

        with (
            mock.patch.object(tts_backend, "probe", return_value=info),
            mock.patch.object(
                tts_backend, "tts_minimax", side_effect=tts_backend.TTSError("cloud down")
            ),
            mock.patch.object(tts_backend, "tts_voicebox", side_effect=fake_vb) as vb,
        ):
            with mock.patch.object(tts_backend, "tts_edge") as edge:
                with tempfile.TemporaryDirectory() as tmp:
                    meta = tts_backend.synthesize(
                        "hello",
                        Path(tmp) / "out.mp3",
                        backend="auto",
                        allow_network_fallback=True,
                    )
        vb.assert_called_once()
        edge.assert_not_called()
        self.assertEqual(meta["backend"], "minimax->voicebox_opt_in_fallback")


if __name__ == "__main__":
    unittest.main()
