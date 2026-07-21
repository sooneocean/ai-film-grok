from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_final  # noqa: E402


class SafeSidecarTests(unittest.TestCase):
    def test_json_writer_replaces_symlink_without_touching_external_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            target = Path(outside) / "target.json"
            target.write_text("untouched", encoding="utf-8")
            sidecar = root / "final-delivery.json"
            sidecar.symlink_to(target)
            render_final.write_json(sidecar, {"ok": True})
            self.assertEqual(target.read_text(encoding="utf-8"), "untouched")
            self.assertFalse(sidecar.is_symlink())
            self.assertEqual(json.loads(sidecar.read_text(encoding="utf-8")), {"ok": True})

    def test_srt_writer_replaces_symlink_without_touching_external_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            target = Path(outside) / "target.srt"
            target.write_text("untouched", encoding="utf-8")
            sidecar = root / "final.srt"
            sidecar.symlink_to(target)
            render_final.write_srt(sidecar, [{"start": 0.0, "end": 1.0, "text": "安全"}])
            self.assertEqual(target.read_text(encoding="utf-8"), "untouched")
            self.assertFalse(sidecar.is_symlink())
            self.assertIn("安全", sidecar.read_text(encoding="utf-8"))

    def test_renderer_explicit_backend_failure_does_not_retry_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            synth = mock.Mock(side_effect=RuntimeError("external failed"))
            with mock.patch.object(render_final, "tts_synthesize", synth):
                with self.assertRaises(render_final.RenderError):
                    render_final.tts_to_wav(
                        "private text",
                        Path(tmp) / "out.mp3",
                        "voice",
                        backend="external",
                    )
            self.assertEqual(synth.call_count, 1)


if __name__ == "__main__":
    unittest.main()
