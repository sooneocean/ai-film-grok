#!/usr/bin/env python3
"""P1/P2 motion core: DF-aware motion gate, variety bulk door, film-core closeout."""

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

from i2v_motion_gate import (  # noqa: E402
    CODE_MEDIUM_MEAN_LOW,
    CODE_MEAT_MEAN_LOW,
    CODE_SOFT_MEAN_LOW,
    MEAN_MEDIUM_FLOOR,
    MEAN_MEAT_FLOOR,
    MEAN_SOFT_FLOOR,
    evaluate_shot_motion,
    floor_for_tier,
    motion_tier_for_shot,
)
from workflow_pack import (  # noqa: E402
    WorkflowPackError,
    assert_variety_preflight,
    bulk_preflight,
    film_core_closeout_audit,
    variety_precheck,
)


def _write(root: Path, rel: str, data: dict | str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(str(data), encoding="utf-8")
    return path


def _meat_spec() -> dict:
    poses = ["cowgirl", "missionary", "from_behind", "side", "standing"]
    sizes = ["ms", "cu", "insert", "insert", "cu"]
    cams = ["push-in", "orbit", "pull-back", "tilt-up", "handheld"]
    shots = []
    for i in range(5):
        shots.append(
            {
                "id": f"shot{i + 1:02d}",
                "heat_phase": "act" if i < 4 else "climax",
                "sex_pose": poses[i],
                "shot_size": sizes[i],
                "duration_sec": 5.0,
                "dramatic_function": "action",
                "dsl": {
                    "motion": f"{cams[i]} slow body thrust, idle not speaking",
                    "camera_axis": cams[i],
                    "action": poses[i],
                    "camera": {"shot_size": sizes[i], "move": cams[i]},
                },
            }
        )
    return {
        "title": "variety-test",
        "heat_scale": "max",
        "director_intent": {"protagonist_want": "escape the island together"},
        "scenes": [{"shots": shots}],
    }


class DfMotionTierTests(unittest.TestCase):
    def test_floors(self) -> None:
        self.assertEqual(floor_for_tier("soft"), MEAN_SOFT_FLOOR)
        self.assertEqual(floor_for_tier("medium"), MEAN_MEDIUM_FLOOR)
        self.assertEqual(floor_for_tier("meat"), MEAN_MEAT_FLOOR)
        self.assertEqual(floor_for_tier("high"), MEAN_MEAT_FLOOR)

    def test_soft_df_reaction(self) -> None:
        self.assertEqual(
            motion_tier_for_shot(heat_phase="setup", dramatic_function="reaction"),
            "soft",
        )
        r = evaluate_shot_motion(
            12.0, heat_phase="setup", dramatic_function="reaction", shot_id="r1"
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["tier"], "soft")
        self.assertEqual(r["floor"], MEAN_SOFT_FLOOR)

    def test_soft_df_below_floor(self) -> None:
        r = evaluate_shot_motion(
            8.0, heat_phase="setup", dramatic_function="insert", shot_id="i1"
        )
        self.assertFalse(r["ok"])
        self.assertIn(CODE_SOFT_MEAN_LOW, r["codes"])

    def test_act_heat_stays_meat_even_with_soft_df(self) -> None:
        self.assertEqual(
            motion_tier_for_shot(heat_phase="act", dramatic_function="reaction"),
            "meat",
        )
        r = evaluate_shot_motion(
            19.0, heat_phase="act", dramatic_function="reaction", shot_id="a1"
        )
        self.assertFalse(r["ok"])
        self.assertIn(CODE_MEAT_MEAN_LOW, r["codes"])

    def test_bare_afterglow_is_medium(self) -> None:
        self.assertEqual(
            motion_tier_for_shot(
                heat_phase="bridge",
                dramatic_function="afterglow",
                wardrobe_state="bare",
            ),
            "medium",
        )
        r = evaluate_shot_motion(
            15.0,
            heat_phase="bridge",
            dramatic_function="afterglow",
            wardrobe_state="bare",
            shot_id="ag1",
        )
        self.assertFalse(r["ok"])
        self.assertIn(CODE_MEDIUM_MEAN_LOW, r["codes"])
        r_ok = evaluate_shot_motion(
            16.0,
            heat_phase="bridge",
            dramatic_function="afterglow",
            wardrobe_state="bare",
            shot_id="ag2",
        )
        self.assertTrue(r_ok["ok"])

    def test_high_df_action(self) -> None:
        self.assertEqual(
            motion_tier_for_shot(heat_phase="setup", dramatic_function="action"),
            "meat",
        )

    def test_spine_tier_fallback(self) -> None:
        self.assertEqual(
            motion_tier_for_shot(heat_phase="setup", spine_tier="soft"),
            "soft",
        )
        self.assertEqual(
            motion_tier_for_shot(heat_phase="setup", spine_tier="high"),
            "meat",
        )


class VarietyBulkDoorTests(unittest.TestCase):
    def test_assert_ok_on_good_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", _meat_spec())
            report = assert_variety_preflight(root, require=True)
            self.assertTrue(report["ok"])

    def test_assert_fails_on_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = _meat_spec()
            for sh in spec["scenes"][0]["shots"]:
                sh["dsl"]["motion"] = "same push-in thrust"
                sh["dsl"]["camera"]["move"] = "push-in"
            _write(root, "film-spec.json", spec)
            with self.assertRaises(WorkflowPackError) as ctx:
                assert_variety_preflight(root, require=True)
            self.assertIn("ADJACENT_MOTION_COLLISION", str(ctx.exception))

    def test_escape_env_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", {"title": "x", "scenes": []})
            with mock.patch.dict(os.environ, {"AIFILM_SKIP_VARIETY_PREFLIGHT": "1"}):
                report = assert_variety_preflight(root, require=True)
            self.assertTrue(report["ok"])
            self.assertTrue(report.get("skipped"))

    def test_bulk_preflight_includes_variety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", _meat_spec())
            _write(root, "manifest.json", {"stills": {}, "clips": {}})
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AIFILM_SKIP_VARIETY_PREFLIGHT", None)
                report = bulk_preflight(
                    root, write=True, probe_tunnel=False, check_lease=False
                )
            names = [c["id"] for c in report.get("checks") or []]
            self.assertIn("variety", names)
            variety = next(c for c in report["checks"] if c["id"] == "variety")
            # good meat variety should pass its own check even if pilot fails
            self.assertTrue(variety.get("ok"), variety)


class FilmCoreCloseoutTests(unittest.TestCase):
    def test_want_and_df_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "x",
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "shot_role": "hero",
                                    "heat_phase": "act",
                                }
                            ]
                        }
                    ],
                },
            )
            _write(
                root,
                "manifest.json",
                {"clips": {"s1": {"path": "clips/s1.mp4"}}},
            )
            audit = film_core_closeout_audit(root, write=True)
            self.assertFalse(audit["ok"])
            codes = {i["code"] for i in audit["issues"]}
            self.assertIn("CORE_WANT_MISSING", codes)
            self.assertIn("CORE_DF_MISSING", codes)
            self.assertTrue((root / "receipts" / "film-core-closeout.json").is_file())

    def test_spine_df_and_dialogue_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spoken = "我们走吧"
            _write(
                root,
                "film-spec.json",
                {
                    "title": "x",
                    "director_intent": {"protagonist_want": "leave together"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "shot_role": "hero",
                                    "dramatic_function": "dialogue",
                                    "audio_cues": [
                                        {
                                            "line_type": "dialogue",
                                            "spoken_text": spoken,
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                },
            )
            _write(
                root,
                "manifest.json",
                {"clips": {"s1": {"path": "clips/s1.mp4"}}},
            )
            spine = (
                f"Dramatic function: dialogue\nWant beat: leave together\n"
                f'Dialogue (Mandarin): "{spoken}"\n'
            )
            _write(root, "receipts/prompts/s1.h3.spine.txt", spine)
            audit = film_core_closeout_audit(root, write=True)
            self.assertTrue(audit["ok"], audit.get("issues"))

    def test_grok_spine_only_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "x",
                    "director_intent": {"protagonist_want": "survive"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "g1",
                                    "shot_role": "hero",
                                    "dramatic_function": "reaction",
                                }
                            ]
                        }
                    ],
                },
            )
            _write(root, "manifest.json", {"clips": {"g1": {"path": "clips/g1.mp4"}}})
            _write(
                root,
                "receipts/prompts/g1.grok.spine.txt",
                "Dramatic function: reaction\nThis beat advances want (reaction): survive\n",
            )
            audit = film_core_closeout_audit(root, write=True)
            self.assertTrue(audit["ok"], audit.get("issues"))
            self.assertEqual(audit["shots"][0].get("spine_engine"), "grok")


class ContinueHandoffMetaTests(unittest.TestCase):
    def test_write_continue_handoff_missing_clip(self) -> None:
        from h3_workflow import _write_continue_handoff

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta = _write_continue_handoff(
                root,
                shot_id="s9",
                shot={
                    "id": "s9",
                    "dramatic_function": "action",
                    "heat_phase": "act",
                },
                deliver=root / "missing.mp4",
                mode="i2v",
                seed=1,
            )
            self.assertFalse(meta["ok"])
            self.assertEqual(meta["dramatic_function"], "action")
            self.assertTrue(
                (root / "receipts" / "continue-handoff" / "s9.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
