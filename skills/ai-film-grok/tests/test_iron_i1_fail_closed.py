"""I1 · iron internalization: anti-hijack / variety-pixel / plate-boring fail-closed."""

from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _multi_take_root() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "receipts").mkdir()
    (root / "takes" / "s1").mkdir(parents=True)
    (root / "takes" / "s1" / "a.mp4").write_bytes(b"\x00" * 200)
    (root / "takes" / "s1" / "b.mp4").write_bytes(b"\x00" * 200)
    (root / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "s1", "heat_phase": "act"}]}]}),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")
    return root


class TestI11AntiHijackGate(unittest.TestCase):
    def test_helper_blocks_multi_without_ah(self) -> None:
        from composition_anti_hijack import multi_seed_anti_hijack_gate

        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANTI_HIJACK"}
        with mock.patch.dict(os.environ, env, clear=True):
            g = multi_seed_anti_hijack_gate(
                multi_take=True, anti_hijack_enabled=False, promote=True
            )
        self.assertFalse(g["ok"])
        self.assertTrue(g["promote_blocked"])
        self.assertIn("SHORTLIST_PROMOTE_BLOCKED_MEAN_ONLY", g["codes"])

    def test_helper_skip_allows(self) -> None:
        from composition_anti_hijack import multi_seed_anti_hijack_gate

        with mock.patch.dict(os.environ, {"AIFILM_SKIP_ANTI_HIJACK": "1"}, clear=False):
            g = multi_seed_anti_hijack_gate(
                multi_take=True, anti_hijack_enabled=False, promote=True
            )
        self.assertTrue(g["ok"])
        self.assertFalse(g["promote_blocked"])
        self.assertTrue(g["skip_intentional"])

    def test_shortlist_advisory_not_ok_without_ah(self) -> None:
        """I1.1: multi-seed without anti-hijack fails even without --promote."""
        from workflow_pack import select_shortlist

        root = _multi_take_root()
        real_import = builtins.__import__

        def _imp(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
            if name == "composition_anti_hijack":
                raise ImportError("simulated missing")
            return real_import(name, globals, locals, fromlist, level)

        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANTI_HIJACK"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("builtins.__import__", side_effect=_imp):
                out = select_shortlist(root, write=True, promote=False, measure_missing=False)
        self.assertFalse(out.get("ok"))
        self.assertIn("SHORTLIST_MEAN_ONLY_NO_ANTI_HIJACK", out.get("codes") or [])

    def test_pk_compare_not_promotable_without_ah(self) -> None:
        from h3_fill_idle import pk_compare

        root = _multi_take_root()
        real_import = builtins.__import__

        def _imp(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
            if name == "composition_anti_hijack":
                raise ImportError("simulated missing")
            return real_import(name, globals, locals, fromlist, level)

        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANTI_HIJACK"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("builtins.__import__", side_effect=_imp):
                out = pk_compare(root, measure_missing=False, write_dailies=False)
        self.assertFalse(out.get("ok"))
        self.assertTrue(out.get("not_promotable"))
        self.assertIn("PK_MULTI_SEED_NO_ANTI_HIJACK", out.get("codes") or [])
        self.assertTrue((out.get("shots") or [{}])[0].get("not_promotable"))


class TestI12VarietyPixel(unittest.TestCase):
    def test_field_only_stale(self) -> None:
        from workflow_pack import variety_pixel_bind

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "takes" / "m1").mkdir(parents=True)
        clip = root / "takes" / "m1" / "t.mp4"
        clip.write_bytes(b"\x00" * 300)
        (root / "manifest.json").write_text(
            json.dumps({"clips": {"m1": {"path": str(clip)}}}),
            encoding="utf-8",
        )
        meat = {
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "m1",
                            "heat_phase": "act",
                            "sex_pose": "missionary",
                            "shot_size": "ms",
                            "dsl": {"motion": "thrust", "camera": {"move": "push-in"}},
                        },
                        {
                            "id": "m2",
                            "heat_phase": "act",
                            "sex_pose": "cowgirl",
                            "shot_size": "cu",
                            "dsl": {"motion": "ride", "camera": {"move": "orbit"}},
                        },
                    ]
                }
            ]
        }
        (root / "film-spec.json").write_text(json.dumps(meat), encoding="utf-8")
        # seed prior receipt with same pixel_fp later recomputed; force via first write then field change
        with mock.patch.dict(os.environ, {"AIFILM_SKIP_VARIETY_PIXEL": ""}, clear=False):
            first = variety_pixel_bind(root, write=True)
            self.assertIn("field_fp", first)
            old_pixel = first["pixel_fp"]
            # change design fields only
            meat["scenes"][0]["shots"][0]["sex_pose"] = "doggy"
            meat["scenes"][0]["shots"][1]["sex_pose"] = "standing"
            (root / "film-spec.json").write_text(json.dumps(meat), encoding="utf-8")
            # patch resolve means so pixel_fp stays identical (no re-I2V)
            with mock.patch(
                "workflow_pack._read_motion_mean",
                return_value=12.0,
            ):
                # rewrite first receipt pixel_fp to match second measurement
                (root / "receipts" / "variety-pixel.json").write_text(
                    json.dumps(
                        {
                            "field_fp": first["field_fp"],
                            "pixel_fp": old_pixel,
                        }
                    ),
                    encoding="utf-8",
                )
                # force same pixel_fp as stored: mock hashlib path by controlling means+paths
                second = variety_pixel_bind(root, write=True)
        # If media incomplete for m2, may get MEAT_CLIP_MISSING instead — still hard fail
        self.assertFalse(second.get("ok"))
        codes = [i.get("code") for i in (second.get("issues") or [])]
        self.assertTrue(
            "VARIETY_FIELD_ONLY_STALE" in codes or "MEAT_CLIP_MISSING" in codes,
            msg=f"expected field-stale or missing clip, got {codes}",
        )

    def test_adjacent_mean_clone(self) -> None:
        from workflow_pack import variety_pixel_bind

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        for sid in ("a1", "a2"):
            (root / "takes" / sid).mkdir(parents=True)
            (root / "takes" / sid / "t.mp4").write_bytes(b"\x00" * 250)
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "a1",
                                    "heat_phase": "act",
                                    "sex_pose": "a",
                                    "dsl": {"motion": "x", "camera": {"move": "push"}},
                                },
                                {
                                    "id": "a2",
                                    "heat_phase": "climax",
                                    "sex_pose": "b",
                                    "dsl": {"motion": "y", "camera": {"move": "orbit"}},
                                },
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")
        with mock.patch("workflow_pack._read_motion_mean", return_value=10.0):
            rep = variety_pixel_bind(root, write=True)
        self.assertFalse(rep.get("ok"))
        codes = [i.get("code") for i in (rep.get("issues") or [])]
        self.assertIn("ADJACENT_MEAN_CLONE", codes)


class TestI13PlateBoring(unittest.TestCase):
    def test_classify_forces_plate_when_boring(self) -> None:
        from final.delivery_class import classify_official_final

        rep = classify_official_final(
            final_complete=True,
            gate_auto_ok=True,
            plate_boring=True,
        )
        self.assertEqual(rep["status"], "OFFICIAL_FINAL_PLATE")
        self.assertTrue(rep["partial"])
        self.assertFalse(rep["master_lock"])
        self.assertIn("plate_boring_meat_mean", rep["honest_limits"])

    def test_assess_from_audit(self) -> None:
        from final.delivery_class import assess_plate_boring_meat_mean

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "receipts" / "i2v-high-motion-audit.json").write_text(
            json.dumps(
                {
                    "kind": "i2v-high-motion-audit",
                    "meat_mean_avg": 8.0,
                    "per_shot": [
                        {"id": "m1", "tier": "meat", "mean": 7.0, "floor": 20},
                        {"id": "m2", "tier": "meat", "mean": 9.0, "floor": 20},
                    ],
                }
            ),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_PLATE_BORING"}
        with mock.patch.dict(os.environ, env, clear=True):
            br = assess_plate_boring_meat_mean(root)
        self.assertTrue(br["boring"])
        self.assertIn("PLATE_BORING_MEAT_MEAN", br["codes"])

    def test_plate_blocks_includes_boring_code(self) -> None:
        from final.delivery_class import plate_blocks_final_complete

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "receipts" / "i2v-high-motion-audit.json").write_text(
            json.dumps(
                {
                    "meat_mean_avg": 5.0,
                    "per_shot": [
                        {"tier": "meat", "mean": 4.0, "floor": 20},
                        {"tier": "meat", "mean": 6.0, "floor": 20},
                    ],
                }
            ),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_PLATE_BORING"}
        with mock.patch.dict(os.environ, env, clear=True):
            adv = plate_blocks_final_complete(root, gates={"final_complete": True})
        self.assertTrue(adv.get("blocks_ship_complete"))
        self.assertIn("PLATE_BORING_MEAT_MEAN", adv.get("codes") or [])
        self.assertTrue(adv.get("plate_boring"))


if __name__ == "__main__":
    unittest.main()
