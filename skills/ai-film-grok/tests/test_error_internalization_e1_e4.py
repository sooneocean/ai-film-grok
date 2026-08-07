#!/usr/bin/env python3
"""E1/E2/E4 · identity generation · partner cast · still provenance (2026-08-07)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class IdentityGenerationLockTests(unittest.TestCase):
    def test_archive_mix_hard_fail(self) -> None:
        from identity_generation_lock import audit_identity_generation

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            man = {
                "clips": {
                    "s01": {
                        "status": "approved",
                        "path": "takes/_archive_pre_leon_restyle/s01.mp4",
                    }
                }
            }
            (root / "film-manifest.json").write_text(
                json.dumps(man), encoding="utf-8"
            )
            rep = audit_identity_generation(root, write_receipt=True)
            self.assertFalse(rep.get("ok"))
            self.assertIn("ARCHIVE_MIX_IN_TIMELINE", rep.get("codes") or [])
            self.assertTrue((root / "receipts" / "cast-generation.json").is_file())

    def test_unverified_identity_partial(self) -> None:
        from identity_generation_lock import audit_identity_generation

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "style-bible.json").write_text(
                json.dumps({"cast_masters": {"hero": "cast/hero.png", "leon": "cast/leon.png"}}),
                encoding="utf-8",
            )
            (root / "film-manifest.json").write_text(
                json.dumps({"clips": {"s01": {"status": "approved", "path": "takes/s01.mp4"}}}),
                encoding="utf-8",
            )
            (root / "receipts" / "face-identity.json").write_text(
                json.dumps({"verified": False, "enrolled": {"hero": {}}}),
                encoding="utf-8",
            )
            rep = audit_identity_generation(root)
            self.assertTrue(rep.get("ok"))
            self.assertTrue(rep.get("identity_partial"))
            self.assertIn("IDENTITY_UNVERIFIED", rep.get("codes") or [])
            self.assertEqual(rep.get("classification"), "IDENTITY_PARTIAL")

    def test_clean_timeline_ok(self) -> None:
        from identity_generation_lock import audit_identity_generation

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "film-manifest.json").write_text(
                json.dumps({"clips": {}}), encoding="utf-8"
            )
            rep = audit_identity_generation(root)
            self.assertTrue(rep.get("ok"))
            self.assertFalse(rep.get("identity_partial"))


class PartnerCastGateTests(unittest.TestCase):
    def test_style_locked_false_green(self) -> None:
        from partner_cast_gate import audit_partner_cast

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "style-bible.json").write_text(
                json.dumps(
                    {
                        "locked": True,
                        "cast_masters": {
                            "hero": {"path": "missing-hero.png"},
                            "leon": {"path": "missing-leon.png"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            rep = audit_partner_cast(root)
            self.assertFalse(rep.get("ok"))
            self.assertIn("STYLE_LOCKED_FALSE_GREEN", rep.get("codes") or [])

    def test_complete_masters_ok(self) -> None:
        from partner_cast_gate import audit_partner_cast

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cast = root / "cast"
            cast.mkdir()
            hero = cast / "hero.png"
            leon = cast / "leon.png"
            hero.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
            leon.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
            (root / "style-bible.json").write_text(
                json.dumps(
                    {
                        "locked": True,
                        "cast_masters": {
                            "hero": {
                                "cast_master": str(hero),
                                "face_lock": str(hero),
                            },
                            "leon": {
                                "cast_master": str(leon),
                                "face_lock": str(leon),
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            rep = audit_partner_cast(root)
            self.assertTrue(rep.get("ok"), rep)


class StillProvenanceTests(unittest.TestCase):
    def test_composite_provenance_raises(self) -> None:
        from still_provenance import StillProvenanceError, assert_still_record_safe_for_i2v

        with self.assertRaises(StillProvenanceError):
            assert_still_record_safe_for_i2v(
                {"path": "stills/s01.png", "still_provenance": "midframe_paste"}
            )

    def test_poison_archive_path_raises(self) -> None:
        from still_provenance import StillProvenanceError, assert_still_record_safe_for_i2v

        with self.assertRaises(StillProvenanceError):
            assert_still_record_safe_for_i2v(
                {"path": "stills/_archive_poison_composite_20260807/s01.png"}
            )

    def test_whole_frame_ok(self) -> None:
        from still_provenance import assert_still_record_safe_for_i2v

        rep = assert_still_record_safe_for_i2v(
            {"path": "stills/s01.png", "still_provenance": "whole_frame"}
        )
        self.assertTrue(rep.get("ok"))


class IronStatusRegistersNewGates(unittest.TestCase):
    def test_new_gate_ids_listed(self) -> None:
        from gates.iron_status import iron_status_report

        rep = iron_status_report()
        ids = {g.get("id") for g in (rep.get("gates") or [])}
        for need in (
            "composition_fill",
            "identity_generation",
            "partner_cast",
            "still_provenance",
            "skip_audit",
        ):
            self.assertIn(need, ids)


class HardDefaultsMemoryLinks(unittest.TestCase):
    """F4 · hard-defaults memory links must resolve (active or archive)."""

    def test_memory_links_exist(self) -> None:
        import re

        hd = (
            Path(__file__).resolve().parents[1]
            / "references"
            / "hard-defaults.md"
        )
        text = hd.read_text(encoding="utf-8")
        refs_dir = hd.parent
        # markdown links to ../memory/...
        links = re.findall(r"\((?:\.\./)+(memory/[^)#\s]+)\)", text)
        missing = []
        for rel in sorted(set(links)):
            # strip any query
            rel = rel.split(" ")[0]
            target = (refs_dir / ".." / rel).resolve()
            # also try relative to skill root
            if not target.is_file():
                target = (refs_dir.parent / rel).resolve()
            if not target.is_file():
                missing.append(rel)
        self.assertEqual(missing, [], f"dead memory links in hard-defaults: {missing}")


if __name__ == "__main__":
    unittest.main()
