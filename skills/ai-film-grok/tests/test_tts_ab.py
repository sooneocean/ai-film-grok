#!/usr/bin/env python3
"""tts-ab: skip unready backends; mock synthesize for edge path."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from tts_ab import run_tts_ab  # noqa: E402


class TTSAbTests(unittest.TestCase):
    def test_skip_voicebox_when_down_edge_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "vo_voice": "zh-CN-XiaoxiaoNeural",
                "shots": [{"id": "shot01", "nar": "话说那天夜里。"}],
            }
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False) + "\n", encoding="utf-8"
            )

            def fake_synth(text, out_mp3, **kwargs):
                p = Path(out_mp3)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"ID3" + b"\x00" * 500)
                return {"backend": kwargs.get("backend") or "edge", "path": str(p), "voice": "zh-CN-XiaoxiaoNeural"}

            with mock.patch("tts_backend.probe") as pr, mock.patch(
                "tts_backend.synthesize", side_effect=fake_synth
            ):
                pr.return_value = {
                    "ok": True,
                    "backends": {"edge": True, "voicebox": False},
                    "ready": {"edge": True, "voicebox": False},
                    "voicebox_ok": False,
                    "voicebox_error": "unreachable",
                }
                # patch at module import site inside run_tts_ab
                with mock.patch.dict("sys.modules"):
                    import tts_backend as tb

                    with mock.patch.object(tb, "probe", pr), mock.patch.object(
                        tb, "synthesize", side_effect=fake_synth
                    ):
                        man = run_tts_ab(
                            root,
                            shot_id="shot01",
                            backends=["edge", "voicebox"],
                        )
            self.assertTrue(man["ok"])
            statuses = {r["backend"]: r["status"] for r in man["results"]}
            self.assertEqual(statuses.get("edge"), "ok")
            self.assertEqual(statuses.get("voicebox"), "skip")
            self.assertTrue(Path(man["manifest_path"]).is_file())

    def test_missing_shot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps({"shots": [{"id": "shot02", "nar": "x"}]}) + "\n",
                encoding="utf-8",
            )
            with mock.patch("tts_backend.probe", return_value={"backends": {"edge": True}, "ready": {"edge": True}}):
                import tts_backend as tb

                with mock.patch.object(tb, "probe", return_value={"backends": {"edge": True}, "ready": {"edge": True}, "voicebox_ok": False}):
                    from tts_ab import TTSAbError

                    with self.assertRaises(TTSAbError):
                        run_tts_ab(root, shot_id="shot01", backends=["edge"])


if __name__ == "__main__":
    unittest.main()
