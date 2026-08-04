#!/usr/bin/env python3
"""v2.37 throughput: auto mean, shortlist promote, ship-prep ladder."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_motion_gate import (  # noqa: E402
    collect_motion_gate_rows,
    measure_mean_absdiff,
    write_mean_sidecar,
)
from workflow_pack import select_shortlist, ship_prep  # noqa: E402


def _write(root: Path, rel: str, data: dict | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for mean measure")
class MeasureMeanTests(unittest.TestCase):
    def test_measure_synthetic_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "t.mp4"
            # 1s color video — low but finite mean if any noise; solid color may be ~0
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=160x280:rate=10",
                    "-t",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    str(mp4),
                ],
                check=True,
            )
            mean = measure_mean_absdiff(mp4)
            self.assertIsNotNone(mean)
            assert mean is not None
            self.assertGreaterEqual(mean, 0.0)
            side = write_mean_sidecar(mp4, mean)
            self.assertTrue(side.is_file())
            data = json.loads(side.read_text(encoding="utf-8"))
            self.assertEqual(data["mean_absdiff"], mean)


class ShortlistPromoteTests(unittest.TestCase):
    def test_promote_writes_manifest_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "t",
                    "heat_scale": "soft",
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "heat_phase": "setup",
                                    "dramatic_function": "reaction",
                                }
                            ]
                        }
                    ],
                },
            )
            _write(root, "manifest.json", {"clips": {}})
            takes = root / "takes" / "s1"
            takes.mkdir(parents=True)
            weak = takes / "a.mp4"
            strong = takes / "b.mp4"
            weak.write_bytes(b"\x00" * 200)
            strong.write_bytes(b"\x00" * 200)
            write_mean_sidecar(weak, 5.0)
            write_mean_sidecar(strong, 22.0)
            rep = select_shortlist(root, write=True, promote=True, measure_missing=False)
            self.assertTrue(rep.get("promoted"))
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(man["clips"]["s1"]["path"]).resolve(), strong.resolve())
            self.assertEqual(man["clips"]["s1"]["mean"], 22.0)
            self.assertEqual(man["clips"]["s1"]["preferred_from"], "select-shortlist")


class ShipPrepTests(unittest.TestCase):
    def test_ship_prep_includes_pk_compare_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "pk",
                    "heat_scale": "soft",
                    "h3": {"enabled": True},
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "shot_role": "hero",
                                    "heat_phase": "setup",
                                    "dramatic_function": "reaction",
                                }
                            ]
                        }
                    ],
                },
            )
            takes = root / "takes" / "s1"
            takes.mkdir(parents=True)
            a = takes / "grok_a.mp4"
            b = takes / "h3_i2v_b.mp4"
            a.write_bytes(b"\x00" * 120_000)
            b.write_bytes(b"\x00" * 150_000)
            write_mean_sidecar(a, 12.0)
            write_mean_sidecar(b, 22.0)
            _write(root, "manifest.json", {"clips": {}, "stills": {}})
            with (
                mock.patch(
                    "workflow_pack.variety_precheck",
                    return_value={"ok": True, "issues": []},
                ),
                mock.patch(
                    "cli_motion.i2v_motion_gate_from_rows",
                    return_value={"ok": True, "row_count": 1},
                ),
                mock.patch(
                    "workflow_pack.film_core_closeout_audit",
                    return_value={"ok": True, "issues": []},
                ),
            ):
                rep = ship_prep(root, measure=False, promote=False, skip_variety=True)
            ids = [s["id"] for s in rep["steps"]]
            self.assertIn("pk_compare", ids)
            self.assertIn("fill_idle_pending", ids)
            pk = next(s for s in rep["steps"] if s["id"] == "pk_compare")
            self.assertTrue(pk.get("advisory"))
            self.assertTrue(pk.get("human_required"))
            self.assertGreaterEqual(int(pk.get("multi_take_count") or 0), 1)
            self.assertTrue(rep.get("human_pk_required"))
            self.assertTrue((root / "receipts" / "pk-compare-ship-prep.json").is_file())
            self.assertTrue((root / "receipts" / "pk-dailies.md").is_file())

    def test_ship_prep_defers_promote_on_multi_take(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "defer",
                    "heat_scale": "soft",
                    "h3": {"enabled": True},
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "shot_role": "hero",
                                    "heat_phase": "setup",
                                    "dramatic_function": "reaction",
                                }
                            ]
                        }
                    ],
                },
            )
            takes = root / "takes" / "s1"
            takes.mkdir(parents=True)
            a = takes / "grok_a.mp4"
            b = takes / "h3_i2v_b.mp4"
            a.write_bytes(b"\x00" * 120_000)
            b.write_bytes(b"\x00" * 150_000)
            write_mean_sidecar(a, 12.0)
            write_mean_sidecar(b, 22.0)
            _write(root, "manifest.json", {"clips": {}, "stills": {}})
            with (
                mock.patch(
                    "workflow_pack.variety_precheck",
                    return_value={"ok": True, "issues": []},
                ),
                mock.patch(
                    "cli_motion.i2v_motion_gate_from_rows",
                    return_value={"ok": True, "row_count": 1},
                ),
                mock.patch(
                    "workflow_pack.film_core_closeout_audit",
                    return_value={"ok": True, "issues": []},
                ),
            ):
                # promote=True would mean-auto-pick H3 — multi-take must defer
                rep = ship_prep(root, measure=False, promote=True, skip_variety=True)
            self.assertTrue(rep.get("promote_deferred_human_pk"))
            self.assertTrue(rep.get("human_pk_required"))
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            # deferred → clips not auto-written by promote
            self.assertFalse(bool((man.get("clips") or {}).get("s1")))

    def test_ship_prep_steps_and_blocks_on_variety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # bad variety: adjacent same motion on meat
            poses = ["cowgirl"] * 5
            shots = []
            for i in range(5):
                shots.append(
                    {
                        "id": f"m{i}",
                        "heat_phase": "act",
                        "sex_pose": poses[i],
                        "shot_size": "ms",
                        "duration_sec": 5.0,
                        "dsl": {
                            "motion": "same push-in thrust",
                            "camera": {"shot_size": "ms", "move": "push-in"},
                        },
                    }
                )
            _write(
                root,
                "film-spec.json",
                {
                    "title": "var-bad",
                    "heat_scale": "max",
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [{"shots": shots}],
                },
            )
            _write(root, "manifest.json", {"clips": {}, "gates": {}})
            with mock.patch(
                "cli_motion.i2v_motion_gate_from_rows",
                return_value={"ok": True, "row_count": 0},
            ):
                rep = ship_prep(root, measure=False, promote=False, skip_variety=False)
            ids = [s["id"] for s in rep["steps"]]
            self.assertIn("variety", ids)
            self.assertIn("i2v_motion_gate", ids)
            self.assertIn("film_core", ids)
            variety = next(s for s in rep["steps"] if s["id"] == "variety")
            self.assertFalse(variety["ok"])
            self.assertFalse(rep["ok"])
            self.assertEqual(rep.get("blocked_by"), "variety")

    def test_ship_prep_ok_path_with_mocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "ok",
                    "heat_scale": "soft",
                    "director_intent": {"protagonist_want": "leave"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "shot_role": "hero",
                                    "dramatic_function": "reaction",
                                    "heat_phase": "setup",
                                }
                            ]
                        }
                    ],
                },
            )
            _write(
                root,
                "manifest.json",
                {
                    "clips": {
                        "s1": {
                            "path": "clips/s1.mp4",
                            "status": "approved",
                            "source_endpoint": "image_to_video",
                        }
                    },
                    "gates": {"clips_complete": True},
                },
            )
            _write(
                root,
                "receipts/prompts/s1.grok.spine.txt",
                "Dramatic function: reaction\nThis beat advances want (reaction): leave\n",
            )
            _write(
                root,
                "receipts/i2v-final-gate.json",
                {"ok": True, "schema_version": 1, "kind": "i2v-final-gate"},
            )
            with mock.patch(
                "workflow_pack.variety_precheck",
                return_value={"ok": True, "issues": []},
            ):
                with mock.patch(
                    "cli_motion.i2v_motion_gate_from_rows",
                    return_value={"ok": True, "row_count": 1},
                ):
                    with mock.patch(
                        "true_video_policy.scan_manifest_true_video",
                        return_value={"ok": True, "checked": 1, "violations": []},
                    ):
                        rep = ship_prep(root, measure=False, promote=False, skip_variety=False)
            self.assertTrue(rep["ok"], rep)
            self.assertTrue((root / "receipts" / "ship-prep.json").is_file())


class CollectRowsMeasureHook(unittest.TestCase):
    def test_collect_uses_sidecar_mean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "heat_phase": "setup",
                                    "dramatic_function": "reaction",
                                }
                            ]
                        }
                    ]
                },
            )
            takes = root / "takes" / "s1"
            takes.mkdir(parents=True)
            mp4 = takes / "x.mp4"
            mp4.write_bytes(b"\x00")
            write_mean_sidecar(mp4, 12.5)
            rows = collect_motion_gate_rows(root, measure_missing=False)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["mean"], 12.5)
            self.assertEqual(rows[0]["dramatic_function"], "reaction")


if __name__ == "__main__":
    unittest.main()
