"""Tests for frw_lipsync.py — FRW cloud lipsync integration.

Previously had ZERO test coverage — the last zero-coverage module.
Tests cover:
  - build_parameters: per-family parameter construction (ltx/wan/seedance)
  - _load_frw_key: env var, .env file, missing key
  - _http_json: HTTP request + response handling (mocked)
  - FrwLipsyncError: error type
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from frw_lipsync import (  # noqa: E402
    DEFAULT_HOST,
    LIPSYNC_MODELS,
    FrwLipsyncError,
    _http_json,
    _load_frw_key,
    build_parameters,
)


class TestBuildParameters(unittest.TestCase):
    """build_parameters constructs per-family API parameters."""

    def test_ltx_family(self):
        params = build_parameters(
            "ltx-lipsync", img_url="http://img", audio_url="http://aud", prompt="test"
        )
        self.assertEqual(params["image_url"], "http://img")
        self.assertEqual(params["audio_url"], "http://aud")
        self.assertEqual(params["prompt"], "test")
        self.assertEqual(params["width"], "720")
        self.assertEqual(params["height"], "1280")
        self.assertEqual(params["video_duration"], "5")
        self.assertEqual(params["video_fps"], "24")

    def test_ltx_default_prompt(self):
        """Empty prompt → default prompt for ltx."""
        params = build_parameters(
            "ltx-lipsync", img_url="http://img", audio_url="http://aud", prompt=""
        )
        self.assertIn("talking head", params["prompt"])

    def test_wan_family(self):
        params = build_parameters(
            "wan-lipsync", img_url="http://img", audio_url="http://aud", prompt="speak"
        )
        self.assertEqual(params["image_url"], "http://img")
        self.assertEqual(params["audio_url"], "http://aud")
        self.assertEqual(params["prompt"], "speak")
        # wan doesn't have width/height
        self.assertNotIn("width", params)

    def test_seedance_family(self):
        params = build_parameters(
            "seedance-2-pro-lipsync", img_url="http://img", audio_url="http://aud", prompt="hi"
        )
        self.assertIsInstance(params["imageUrls"], list)
        self.assertEqual(params["imageUrls"], ["http://img"])
        self.assertEqual(params["audioUrl"], "http://aud")
        self.assertEqual(params["aspectRatio"], "9:16")
        self.assertEqual(params["resolution"], "720p")
        self.assertEqual(params["generate_audio"], "false")

    def test_all_models_have_build_params(self):
        """Every model in LIPSYNC_MODELS can build parameters."""
        for model in LIPSYNC_MODELS:
            params = build_parameters(model, img_url="http://i", audio_url="http://a", prompt="p")
            self.assertIsInstance(params, dict)
            self.assertTrue(len(params) > 0)


class TestLoadFrwKey(unittest.TestCase):
    """_load_frw_key resolves FRW_API_KEY from env or .env file."""

    def test_env_key(self):
        """FRW_API_KEY in env → returned with source label."""
        with mock.patch.dict(os.environ, {"FRW_API_KEY": "test_key_123"}):
            key, src = _load_frw_key()
            self.assertEqual(key, "test_key_123")
            self.assertIn("env", src)

    def test_missing_key_raises(self):
        """No key anywhere → FrwLipsyncError."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Also mock home to avoid real .env files
            with mock.patch.object(Path, "home", return_value=Path("/nonexistent")):
                with self.assertRaises(FrwLipsyncError) as ctx:
                    _load_frw_key()
                self.assertIn("missing", str(ctx.exception))

    def test_env_takes_precedence_over_file(self):
        """Env key wins even if .env file exists."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            # Create a fake .env
            frw_dir = Path(tmp) / "frwclaw-pro"
            frw_dir.mkdir()
            env_file = frw_dir / ".env"
            env_file.write_text("FRW_API_KEY=from_file\n")

            with mock.patch.dict(os.environ, {"FRW_API_KEY": "from_env"}):
                with mock.patch.object(Path, "home", return_value=Path(tmp)):
                    key, src = _load_frw_key()
                    self.assertEqual(key, "from_env")
                    self.assertIn("env", src)


class TestHttpJson(unittest.TestCase):
    """_http_json makes HTTP requests and returns (status, body)."""

    def test_success_response(self):
        """200 response → returns (200, parsed_body)."""
        import urllib.error
        import urllib.request

        mock_resp = mock.MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.object(urllib.request, "urlopen", return_value=mock_resp):
            status, body = _http_json("GET", "http://test", api_key="key")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})

    def test_http_error_response(self):
        """HTTPError → returns (code, parsed_error_body)."""
        import urllib.error
        import urllib.request

        exc = urllib.error.HTTPError(
            url="http://test",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        exc.read = mock.MagicMock(return_value=b'{"error": "no permission"}')

        with mock.patch.object(urllib.request, "urlopen", side_effect=exc):
            status, body = _http_json("POST", "http://test", api_key="key")
        self.assertEqual(status, 403)
        self.assertEqual(body, {"error": "no permission"})

    def test_post_with_body(self):
        """POST with body → Content-Type set, data sent."""
        import urllib.request

        captured_req = []

        mock_resp = mock.MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = b'{"task_id": "abc"}'
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        def capture(req, **kwargs):
            captured_req.append(req)
            return mock_resp

        with mock.patch.object(urllib.request, "urlopen", side_effect=capture):
            status, body = _http_json("POST", "http://test", api_key="k", body={"data": 1})

        self.assertEqual(status, 201)
        self.assertEqual(body, {"task_id": "abc"})
        # Verify request had Content-Type header (urllib normalizes case)
        req = captured_req[0]
        headers_lower = {k.lower(): v for k, v in req.headers.items()}
        self.assertIn("content-type", headers_lower)

    def test_empty_response_body(self):
        """Empty response → returns (status, {})."""
        import urllib.request

        mock_resp = mock.MagicMock()
        mock_resp.status = 204
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.object(urllib.request, "urlopen", return_value=mock_resp):
            status, body = _http_json("GET", "http://test", api_key="k")
        self.assertEqual(status, 204)
        self.assertEqual(body, {})


class TestLipsyncModels(unittest.TestCase):
    """LIPSYNC_MODELS registry structure."""

    def test_all_models_have_required_fields(self):
        for name, meta in LIPSYNC_MODELS.items():
            self.assertIn("template_id", meta, f"{name} missing template_id")
            self.assertIn("family", meta, f"{name} missing family")
            self.assertIn("register_endpoint", meta, f"{name} missing register_endpoint")

    def test_families_are_known(self):
        valid_families = {"ltx", "wan", "seedance"}
        for name, meta in LIPSYNC_MODELS.items():
            self.assertIn(meta["family"], valid_families, f"{name} has unknown family")

    def test_default_host_is_url(self):
        self.assertTrue(DEFAULT_HOST.startswith("http"))


if __name__ == "__main__":
    unittest.main()
