#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from asset_registry import (  # noqa: E402
    assets_check,
    lint_locations,
    registry_path,
    sync_assets,
)
from story_plan import run_plan  # noqa: E402


class AssetRegistryTests(unittest.TestCase):
    def test_assets_parser_domain_preserves_sync_safety_flags(self) -> None:
        from cli_assets import add_assets_parsers

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="cmd", required=True)
        add_assets_parsers(subparsers)

        sync = parser.parse_args(
            ["assets", "sync", "--root", "film", "--force", "--no-write", "--no-graph"]
        )
        status = parser.parse_args(["assets", "status", "--root", "film", "--sync"])
        check = parser.parse_args(["assets", "check", "--root", "film", "--no-sync"])

        self.assertTrue(sync.force)
        self.assertTrue(sync.no_write)
        self.assertTrue(sync.no_graph)
        self.assertTrue(status.sync)
        self.assertTrue(check.no_sync)

    def test_sync_dry_run_does_not_create_asset_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            report = sync_assets(root, write=False)

            self.assertTrue(report.get("ok"), report)
            self.assertFalse((root / "canonical").exists())
            self.assertFalse(registry_path(root).exists())
            self.assertFalse((root / "style-bible.json").exists())
            self.assertFalse((root / "receipts").exists())

    def test_check_without_sync_fails_closed_when_registry_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            report = assets_check(root, sync_first=False)

            self.assertFalse(report.get("ok"), report)
            self.assertIn("ASSET_REGISTRY_MISSING", report.get("issues") or [])
            self.assertFalse((root / "canonical").exists())
            self.assertFalse(registry_path(root).exists())
            self.assertFalse((root / "style-bible.json").exists())
            self.assertFalse((root / "receipts").exists())

    def test_plan_then_assets_aligned(self) -> None:
        idea = "雨夜出租车里，女司机与乘客靠近，雨衣半敞。"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = run_plan(root, idea, title="雨夜", target_duration=36, force=True)
            self.assertTrue(plan.get("ok"), plan)
            self.assertTrue((plan.get("assets") or {}).get("ok") is not False)

            rep = sync_assets(root, write=True)
            self.assertTrue(rep.get("ok"), rep)
            self.assertTrue(registry_path(root).is_file())
            self.assertGreaterEqual(rep["counts"]["characters"], 1)
            self.assertGreaterEqual(rep["counts"]["locations"], 1)

            bible = json.loads((root / "style-bible.json").read_text(encoding="utf-8"))
            # locations structured as objects
            locs = bible.get("locations") or {}
            self.assertTrue(locs)
            for _lid, val in locs.items():
                self.assertIsInstance(val, dict)
                self.assertIn("description", val)

            # wardrobe variants include full
            wv = bible.get("wardrobe_variants") or {}
            self.assertTrue(wv)
            for _cid, block in wv.items():
                self.assertIn("full", block)

            # cast_state_masters slots
            csm = bible.get("cast_state_masters") or {}
            self.assertTrue(csm)

            # graph got characterStates
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            self.assertIn("characterStates", graph)
            self.assertTrue(graph.get("assetRegistry"))

            # dirs created
            for cid in rep.get("characters") or []:
                self.assertTrue((root / "canonical" / "cast-states" / cid).is_dir())

            chk = assets_check(root, sync_first=True)
            # no re-dress on monotonic full plan
            self.assertEqual(chk.get("re_dress_risks"), 0)
            # full-only wardrobe: no used undress → should be aligned
            self.assertTrue(chk.get("ok"), chk)

    def test_re_dress_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "一间卧室里的短戏足够长。", title="test", force=True)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            shots = []
            for sc in spec.get("scenes") or []:
                shots.extend(sc.get("shots") or [])
            self.assertGreaterEqual(len(shots), 2)
            shots[0]["wardrobe_state"] = "undressed"
            shots[1]["wardrobe_state"] = "full"  # re-dress
            if isinstance(shots[0].get("dsl"), dict):
                shots[0]["dsl"]["wardrobe_state"] = "undressed"
            if isinstance(shots[1].get("dsl"), dict):
                shots[1]["dsl"]["wardrobe_state"] = "full"
            # write back
            si = 0
            for sc in spec["scenes"]:
                n = len(sc.get("shots") or [])
                sc["shots"] = shots[si : si + n]
                si += n
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            rep = sync_assets(root, write=True)
            self.assertGreaterEqual(rep["counts"]["re_dress_risks"], 1)
            chk = assets_check(root, sync_first=False)
            self.assertFalse(chk.get("ok"))
            self.assertTrue(any("re_dress" in x for x in (chk.get("issues") or [])))

    def test_prop_harvest_from_dsl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "咖啡馆里的相遇，杯子很重要。", force=True)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            for sc in spec.get("scenes") or []:
                for sh in sc.get("shots") or []:
                    dsl = sh.setdefault("dsl", {})
                    dsl["props"] = ["coffee cup", "umbrella"]
                    break
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            rep = sync_assets(root, write=True)
            self.assertGreaterEqual(rep["counts"]["props"], 1)
            bible = json.loads((root / "style-bible.json").read_text(encoding="utf-8"))
            props = bible.get("props") or {}
            self.assertTrue(any(isinstance(v, dict) for v in props.values()))


class LintLocationsTests(unittest.TestCase):
    """P3-13: scene art / location continuity lint."""

    def test_unregistered_location_triggers_warning(self):
        shots = [{"id": "s1", "locationId": "unknown"}]
        locs = [{"id": "alley"}]
        rep = lint_locations(shots, locs)
        self.assertFalse(rep["ok"])
        self.assertIn("SCENE_LOCATION_UNREGISTERED", rep["codes"])

    def test_registered_location_no_issue(self):
        shots = [{"id": "s1", "locationId": "alley", "dsl": {"subject": "woman"}}]
        locs = [{"id": "alley"}]
        rep = lint_locations(shots, locs)
        self.assertTrue(rep["ok"])

    def test_recurring_object_in_dsl_key_no_issue(self):
        """Recurring object mentioned as a dsl key → no issue."""
        shots = [{"id": "s1", "locationId": "alley", "dsl": {"subject": "woman", "rain": "wet"}}]
        locs = [{"id": "alley", "recurringObjects": ["rain"]}]
        rep = lint_locations(shots, locs)
        self.assertNotIn("SCENE_RECURRING_OBJECT_MISSING", rep["codes"])

    def test_recurring_object_missing_triggers_warning(self):
        shots = [{"id": "s1", "locationId": "alley", "dsl": {"subject": "woman"}}]
        locs = [{"id": "alley", "recurringObjects": ["streetlamp"]}]
        rep = lint_locations(shots, locs)
        self.assertIn("SCENE_RECURRING_OBJECT_MISSING", rep["codes"])

    def test_empty_shots_no_issues(self):
        rep = lint_locations([], [{"id": "alley"}])
        self.assertTrue(rep["ok"])

    def test_no_locations_no_issues(self):
        rep = lint_locations([{"id": "s1", "locationId": "alley"}], None)
        self.assertTrue(rep["ok"])


if __name__ == "__main__":
    unittest.main()
