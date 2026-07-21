"""compose-preview helpers: URL extract + preview receipt (no long-lived server)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compose_preview import (  # noqa: E402
    extract_urls,
    has_valid_preview_receipt,
    load_preview_receipt,
    prefer_studio_url,
    write_preview_receipt,
)
from compose_render import ComposeRenderError, assert_preview_receipt  # noqa: E402


class UrlParseTests(unittest.TestCase):
    def test_extract_and_prefer_localhost(self) -> None:
        text = """
  Project   demo
  Studio    http://localhost:3002
  Other https://example.com/x
"""
        urls = extract_urls(text)
        self.assertIn("http://localhost:3002", urls)
        self.assertEqual(prefer_studio_url(urls), "http://localhost:3002")

    def test_empty(self) -> None:
        self.assertEqual(extract_urls(""), [])
        self.assertIsNone(prefer_studio_url([]))


class PreviewReceiptTests(unittest.TestCase):
    def test_write_and_validate_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(has_valid_preview_receipt(root))
            path = write_preview_receipt(
                root,
                url="http://localhost:3002",
                hf_dir=str(root / "compose" / "hyperframes"),
                already_running=False,
                port=3002,
            )
            self.assertTrue(path.is_file())
            self.assertTrue(has_valid_preview_receipt(root))
            rec = load_preview_receipt(root)
            assert rec is not None
            self.assertEqual(rec["kind"], "compose-preview-receipt")
            self.assertEqual(rec["url"], "http://localhost:3002")
            # legacy pointer
            meta = json.loads((root / "compose" / "preview.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["url"], "http://localhost:3002")
            self.assertEqual(meta["receipt"], "receipts/compose-preview.json")

    def test_assert_preview_receipt_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ComposeRenderError) as ctx:
                assert_preview_receipt(root)
            self.assertIn("require-preview", str(ctx.exception))
            write_preview_receipt(
                root, url="http://127.0.0.1:3002", hf_dir=str(root / "hf")
            )
            info = assert_preview_receipt(root)
            self.assertTrue(info["ok"])
            self.assertIn("127.0.0.1", str(info["url"]))


if __name__ == "__main__":
    unittest.main()
