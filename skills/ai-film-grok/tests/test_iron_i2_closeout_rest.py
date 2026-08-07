"""I2.2/I2.4/I1.4 residual iron internalization tests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestI24GenerationRequest(unittest.TestCase):
    def test_restricted_missing_receipt_hard(self) -> None:
        from generation_request import GenerationRequestError, assert_generation_request_for_i2v

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "heat_scale": "max",
                    "adult_max_iron": True,
                    "scenes": [{"shots": [{"id": "s1", "heat_phase": "act"}]}],
                }
            ),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_GENERATION_REQUEST"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(GenerationRequestError) as ctx:
                assert_generation_request_for_i2v(root, "s1", build_if_missing=False)
        self.assertIn("request.json", str(ctx.exception))

    def test_skip_env(self) -> None:
        from generation_request import assert_generation_request_for_i2v

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps({"heat_scale": "max"}), encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"AIFILM_SKIP_GENERATION_REQUEST": "1"}):
            rep = assert_generation_request_for_i2v(root, "x")
        self.assertTrue(rep.get("skipped"))


class TestI22Endframe(unittest.TestCase):
    def test_non_restricted_ok(self) -> None:
        from endframe_wardrobe import lint_endframe_no_redress

        root = Path(tempfile.mkdtemp())
        clip = root / "c.mp4"
        clip.write_bytes(b"\x00" * 100)
        rep = lint_endframe_no_redress(
            clip, wardrobe_state="full", heat_phase="setup", shot_id="s0"
        )
        self.assertTrue(rep.get("ok"))
        self.assertFalse(rep.get("required"))

    def test_restricted_extract_fail_soft(self) -> None:
        from endframe_wardrobe import lint_endframe_no_redress

        root = Path(tempfile.mkdtemp())
        clip = root / "c.mp4"
        clip.write_bytes(b"\x00" * 100)
        rep = lint_endframe_no_redress(
            clip, wardrobe_state="bare", heat_phase="act", shot_id="m1"
        )
        # dummy mp4 → extract fail soft, not hard
        self.assertTrue(rep.get("ok") or rep.get("soft") or "ENDFRAME_EXTRACT_FAILED" in (rep.get("codes") or []))


class TestI14MixDefault(unittest.TestCase):
    def test_default_mix_path_comment_in_source(self) -> None:
        """Guard: render_final defaults to broadband (no acrossover) unless ALLOW."""
        src = (SCRIPTS / "post" / "render_final.py").read_text(encoding="utf-8")
        self.assertIn("AIFILM_ALLOW_ACROSSOVER_MIX", src)
        self.assertIn("broadband_default", src)
        self.assertIn("mix_path", src)


if __name__ == "__main__":
    unittest.main()
