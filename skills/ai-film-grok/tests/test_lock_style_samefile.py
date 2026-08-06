"""lock-style same-path short-circuit — shipped aifilm_grok.cmd_lock_style."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok as ag  # noqa: E402


class LockStyleSameFileTests(unittest.TestCase):
    def test_lock_style_when_canonical_already_at_dest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            # init-like skeleton
            for name in ("canonical", "keyframes", "clips", "audio", "out", "prompts", "receipts"):
                (root / name).mkdir(parents=True)
            style_path = root / "canonical" / "style-v1.jpg"
            style_path.write_bytes(b"\xff\xd8\xff\xd9fakejpeg")
            style_bible = {
                "schema_version": 1,
                "locked": False,
                "title": "samefile-test",
                "medium": "high-quality anime illustration",
                "palette": "silver hair, cold blue night, violet rim",
                "lighting": "night practicals",
                "lens": "vertical 9:16",
                "rendering": "clean anime linework",
                "signature_block": (
                    "Vertical consistent anime short, clean linework, "
                    "coherent palette, stable cast identity across shots."
                ),
                "identity_lock": (
                    "Adult anime woman: long silver hair, purple-red eyes, "
                    "white jacket, black thigh-high socks"
                ),
                "negative_hints": "do not change face identity",
                "canonical_style_path": None,
            }
            (root / "style-bible.json").write_text(
                json.dumps(style_bible, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "title": "samefile-test",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "gates": {},
                        "media": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (root / "brief.json").write_text("{}", encoding="utf-8")
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            (root / "timeline.json").write_text("{}", encoding="utf-8")

            locked_sig = (
                "Locked vertical anime short, clean linework, coherent night palette, "
                "stable cast identity and wardrobe across all shots."
            )
            args = argparse.Namespace(
                root=str(root),
                canonical=str(style_path),  # same file as dest
                cast_master=None,
                signature=locked_sig,
            )
            # Must not raise SameFileError
            rc = ag.cmd_lock_style(args)
            self.assertEqual(rc, 0)
            out = json.loads((root / "style-bible.json").read_text(encoding="utf-8"))
            self.assertTrue(out["locked"])
            self.assertEqual(Path(out["canonical_style_path"]).resolve(), style_path.resolve())
            self.assertTrue(out.get("canonical_style_sha256"))
            self.assertEqual(out.get("signature_block"), locked_sig)


if __name__ == "__main__":
    unittest.main()
