"""H2 · compose hotpath contracts (fast path — no ffmpeg / no slow marker).

Locks fail-closed surfaces that must never regress on the designed-post path:

- underlay + burned_in plate → double-burn blocked
- layout=auto with film_final present → underlay risk surface
- multiclip allows burned plates (not underlay)
- HyperFrames register_final fails closed when caption gate returns ok=false
- empty/missing delivery burned_in is unknown (None), not a free pass claim
"""

from __future__ import annotations

import pytest

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from compose_render import (  # noqa: E402
    ComposeRenderError,
    assert_underlay_not_double_burn,
    plate_subtitles_burned_in,
    register_final_film,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DoubleBurnFastPathTests(unittest.TestCase):
    def test_underlay_blocks_when_burned_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            _write(
                root / "out" / "final-delivery.json",
                json.dumps(
                    {
                        "subtitles": {
                            "burned_in": True,
                            "caption_owner": "ffmpeg",
                        }
                    }
                ),
            )
            with self.assertRaises(ComposeRenderError) as ctx:
                assert_underlay_not_double_burn(root, layout="underlay")
            self.assertIn("double-burn", str(ctx.exception).lower())

    def test_auto_layout_with_final_uses_underlay_and_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "film_final.mp4").write_bytes(b"fake")
            _write(
                root / "out" / "final-delivery.json",
                json.dumps({"subtitles": {"burned_in": True}}),
            )
            with self.assertRaises(ComposeRenderError) as ctx:
                assert_underlay_not_double_burn(root, layout="auto")
            self.assertIn("double-burn", str(ctx.exception).lower())

    def test_multiclip_allows_burned_plate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            _write(
                root / "out" / "final-delivery.json",
                json.dumps({"subtitles": {"burned_in": True}}),
            )
            info = assert_underlay_not_double_burn(root, layout="multiclip")
            self.assertTrue(info["ok"])
            self.assertEqual(info.get("layout"), "multiclip")

    def test_allow_burned_underlay_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            _write(
                root / "out" / "final-delivery.json",
                json.dumps({"subtitles": {"burned_in": True}}),
            )
            info = assert_underlay_not_double_burn(
                root, layout="underlay", allow_burned_underlay=True
            )
            self.assertTrue(info["ok"])
            self.assertTrue(info.get("skipped"))

    def test_subs_off_allows_underlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            _write(
                root / "out" / "final-delivery.json",
                json.dumps(
                    {
                        "subtitles": {
                            "burned_in": False,
                            "caption_owner": None,
                        }
                    }
                ),
            )
            info = assert_underlay_not_double_burn(root, layout="underlay")
            self.assertTrue(info["ok"])
            self.assertIs(info.get("burned_in"), False)

    def test_missing_delivery_burned_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            self.assertIsNone(plate_subtitles_burned_in(root))
            # unknown burned_in does not hard-block underlay
            info = assert_underlay_not_double_burn(root, layout="underlay")
            self.assertTrue(info["ok"])
            self.assertIsNone(info.get("burned_in"))


class HyperframesRegisterCaptionGateTests(unittest.TestCase):
    def test_hf_register_fails_closed_when_caption_gate_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            src = root / "out" / "hf_src.mp4"
            src.write_bytes(b"fake-mp4")
            _write(root / "manifest.json", json.dumps({"outputs": {}, "gates": {}}))
            with mock.patch(
                "final_stages.ensure_captions_after_hf",
                return_value={
                    "ok": False,
                    "caption_owner": "missing",
                    "error": "HyperFrames captions not visible in pixels",
                },
            ):
                with self.assertRaises(ComposeRenderError) as ctx:
                    register_final_film(
                        root,
                        src,
                        post_engine="hyperframes",
                        require_motion=False,
                        force=True,
                    )
            msg = str(ctx.exception).lower()
            self.assertIn("caption", msg)

    def test_non_hf_engine_skips_caption_gate(self) -> None:
        """ffmpeg engine must not call HF caption ownership (plate burn path)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            src = root / "out" / "src.mp4"
            src.write_bytes(b"fake")
            _write(root / "manifest.json", json.dumps({"outputs": {}, "gates": {}}))
            with mock.patch(
                "final_stages.ensure_captions_after_hf",
                side_effect=AssertionError("HF gate must not run for ffmpeg engine"),
            ):
                with mock.patch(
                    "compose_render.analyze_media",
                    return_value={
                        "ok": True,
                        "duration_sec": 1.0,
                        "errors": [],
                    },
                ):
                    with mock.patch("compose_render.pdur", return_value=1.0):
                        with mock.patch(
                            "compose_render.sha256",
                            return_value="a" * 64,
                        ):
                            result = register_final_film(
                                root,
                                src,
                                post_engine="ffmpeg",
                                require_motion=False,
                                force=True,
                            )
            self.assertTrue(result["ok"])
            self.assertEqual(result.get("post_engine"), "ffmpeg")


if __name__ == "__main__":
    unittest.main()
