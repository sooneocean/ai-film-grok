"""Hot-path delivery contracts (Batch D · ROI 2026-08-03 · P2 2026-08-05).

Locks lesson-backed invariants that must not regress:

- final stages receipt names plate ``subs off`` + HyperFrames caption ownership
- HF caption gate fails closed when pixel probe is explicitly negative
- heat final/media gates fail closed if ``heat_check`` cannot be imported
- plate double-burn guard still rejects burned-in underlay plates
- caption_path master_hf / ship_hardburn plate rules (no double layer)
- SRT non-overlap clamp on write_srt
- mix PARTIAL v2 honesty fields
- ship path may allow_burned_underlay; default underlay still hard-blocks burn

These complement test_final_stages / test_compose_render / test_adult_max_wave6
without re-testing happy-path bulk.
"""

from __future__ import annotations

import pytest

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

import final_stages  # noqa: E402
from final.delivery_class import plate_blocks_final_complete  # noqa: E402
from compose_render import ComposeRenderError, assert_underlay_not_double_burn  # noqa: E402
from h3_fill_idle import fill_idle_until_empty, run_next_fill_idle  # noqa: E402
from longform import estimate_plate_timeout  # noqa: E402
from final.manifest import build_final_film_manifest_entry  # noqa: E402
from mix_partial import write_final_mix_partial_receipt  # noqa: E402
from post_doctor import run_post_doctor  # noqa: E402
from post_route import (  # noqa: E402
    PostRouteError,
    apply_route_to_plate,
    assert_no_double_caption_layers,
    resolve_caption_path,
)
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_heat_allows_final,
    assert_heat_allows_media,
)
from render_final import write_srt  # noqa: E402
from timeline_clock import audit_timeline_clock, rewrite_timeline_from_film  # noqa: E402
from util import write_json  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FinalStagesContractTests(unittest.TestCase):
    def test_stages_receipt_locks_plate_subs_off_and_hf_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = final_stages.write_stages_receipt(
                root,
                {
                    "plate": {"ok": True, "subs": "off"},
                    "hf": {"ok": True},
                    "caption": {"ok": True, "caption_owner": "hyperframes"},
                    "deliver": {"ok": True},
                },
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            contract = data.get("contract") or []
            joined = "\n".join(str(c) for c in contract).lower()
            self.assertEqual(data.get("kind"), "final-stages")
            self.assertEqual(len(contract), 4)
            self.assertIn("subs off", joined)
            self.assertIn("hyperframes", joined)
            self.assertIn("pil_recovery", joined)
            self.assertIn("burned_in", joined)

    def test_export_ok_but_pixel_false_fails_closed(self) -> None:
        """Export-only path requires inconclusive probe (None), not a hard False."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "out" / "final.srt", "1\n00:00:01,000 --> 00:00:03,000\nhi\n")
            final_mp4 = root / "out" / "final.mp4"
            _write(final_mp4, "fake")
            with mock.patch.object(
                final_stages,
                "inspect_hf_caption_export",
                return_value={"ok": True, "captions_in_index_html": 9},
            ):
                with mock.patch.object(
                    final_stages,
                    "sample_bottom_band_activity",
                    return_value={"ok": False, "likely_count": 0},
                ):
                    result = final_stages.ensure_captions_after_hf(root, final_mp4=final_mp4)
            self.assertFalse(result["ok"])
            self.assertEqual(result["caption_owner"], "missing")
            self.assertIn("HyperFrames", result.get("error") or "")

    def test_patch_delivery_never_claims_burn_when_owner_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            delivery = root / "out" / "final-delivery.json"
            _write(delivery, json.dumps({"subtitles": {"burned_in": True, "caption_owner": "x"}}))
            final_stages.patch_delivery_burned_in(root, burned_in=False, owner="missing")
            data = json.loads(delivery.read_text(encoding="utf-8"))
            self.assertFalse(data["subtitles"]["burned_in"])
            self.assertEqual(data["subtitles"]["caption_owner"], "missing")


class HeatGateFailClosedTests(unittest.TestCase):
    def test_final_gate_fails_closed_when_heat_check_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_import = __import__

            def _blocked(name, *args, **kwargs):
                if name == "heat_check" or name.endswith(".heat_check"):
                    raise ImportError("simulated missing heat_check")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=_blocked):
                with self.assertRaises(ProductionGateError) as ctx:
                    assert_heat_allows_final(root, env_skip=False)
            self.assertIn("heat_check unavailable", str(ctx.exception))

    def test_media_gate_fails_closed_when_heat_check_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_import = __import__

            def _blocked(name, *args, **kwargs):
                if name == "heat_check" or (isinstance(name, str) and name.endswith("heat_check")):
                    raise ImportError("simulated missing heat_check")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=_blocked):
                with self.assertRaises(ProductionGateError) as ctx:
                    assert_heat_allows_media(root, env_skip=False)
            self.assertIn("heat_check unavailable", str(ctx.exception))

    def test_final_gate_blocks_when_status_hard_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_status = {
                "active": True,
                "hard_fail": True,
                "final_ok": False,
                "needs_boost": True,
                "score": 12,
                "grade": "D",
                "why": "impact too low",
            }
            with mock.patch("heat_check.heat_agent_status", return_value=fake_status):
                with self.assertRaises(ProductionGateError) as ctx:
                    assert_heat_allows_final(root, env_skip=False)
            msg = str(ctx.exception).lower()
            self.assertIn("heat final gate", msg)
            self.assertIn("hard block", msg)


class DoubleBurnPlateTests(unittest.TestCase):
    def test_burned_in_plate_blocks_underlay_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "out" / "plate.mp4"
            _write(plate, "fake-plate")
            _write(
                root / "out" / "final-delivery.json",
                json.dumps(
                    {
                        "plate": str(plate),
                        "subtitles": {"burned_in": True, "caption_owner": "ffmpeg"},
                    }
                ),
            )
            with self.assertRaises(ComposeRenderError) as ctx:
                assert_underlay_not_double_burn(root, layout="underlay")
            self.assertIn("double-burn", str(ctx.exception).lower())

    def test_subs_off_plate_allows_underlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "out" / "plate.mp4"
            _write(plate, "fake-plate")
            _write(
                root / "out" / "final-delivery.json",
                json.dumps(
                    {
                        "plate": str(plate),
                        "subtitles": {"burned_in": False, "caption_owner": None},
                    }
                ),
            )
            info = assert_underlay_not_double_burn(root, layout="underlay")
            self.assertTrue(info.get("ok", True) or info is not None)

    def test_allow_burned_underlay_skips_double_burn_gate(self) -> None:
        """ship_hardburn path may grade/title on burned plate with explicit allow."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "out" / "plate.mp4"
            _write(plate, "fake-plate")
            _write(
                root / "out" / "final-delivery.json",
                json.dumps(
                    {
                        "plate": str(plate),
                        "subtitles": {"burned_in": True, "caption_owner": "ffmpeg_plate"},
                    }
                ),
            )
            info = assert_underlay_not_double_burn(
                root, layout="underlay", allow_burned_underlay=True
            )
            self.assertTrue(info.get("ok"))
            self.assertTrue(info.get("skipped"))


class CaptionPathHotpathTests(unittest.TestCase):
    def test_master_hf_forbids_plate_burn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            route = resolve_caption_path(root, post_engine="hyperframes")
            self.assertEqual(route["caption_path"], "master_hf")
            plate = apply_route_to_plate(route, subs_mode=None, plate_cards="auto")
            self.assertEqual(plate["subs"], "off")
            with self.assertRaises(PostRouteError):
                apply_route_to_plate(route, subs_mode="burn", plate_cards="blank")

    def test_ship_hardburn_forces_burn_and_allow_underlay_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            route = resolve_caption_path(
                root, post_engine="hyperframes", explicit="ship_hardburn"
            )
            self.assertEqual(route["caption_path"], "ship_hardburn")
            self.assertTrue(route["allow_burned_underlay"])
            plate = apply_route_to_plate(route, subs_mode="off", plate_cards="auto")
            self.assertEqual(plate["subs"], "burn")

    def test_assert_no_double_caption_layers_ship_plus_hf_owner(self) -> None:
        with self.assertRaises(PostRouteError):
            assert_no_double_caption_layers(
                caption_path="ship_hardburn",
                plate_subs="burn",
                caption_owner="hyperframes",
            )

    def test_env_force_ship_hardburn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict(os.environ, {"AIFILM_CAPTION_PATH": "ship_hardburn"}, clear=False):
                route = resolve_caption_path(root, post_engine="hyperframes")
            self.assertEqual(route["caption_path"], "ship_hardburn")
            self.assertIn("env", str(route.get("source") or "").lower())

    def test_spec_caption_path_overrides_default_hf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "film-spec.json", {"post": {"caption_path": "ship_hardburn"}})
            route = resolve_caption_path(root, post_engine="hyperframes")
            self.assertEqual(route["caption_path"], "ship_hardburn")

    def test_master_hf_ok_with_subs_off_and_hf_owner(self) -> None:
        assert_no_double_caption_layers(
            caption_path="master_hf",
            plate_subs="off",
            caption_owner="hyperframes",
        )


class SrtNonOverlapHotpathTests(unittest.TestCase):
    def test_write_srt_clamps_overlapping_cues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "final.srt"
            write_srt(
                path,
                [
                    {"start": 0.0, "end": 2.0, "text": "甲"},
                    {"start": 1.0, "end": 3.0, "text": "乙"},  # overlaps previous
                ],
            )
            text = path.read_text(encoding="utf-8")
            # second cue must start at/after previous end → no SRT_OVERLAP for post_doctor
            self.assertIn("甲", text)
            self.assertIn("乙", text)
            # 00:00:02,000 appears as clamped start for cue 2
            self.assertIn("00:00:02,000", text)


class MixPartialHotpathTests(unittest.TestCase):
    def test_partial_receipt_v2_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mixed = root / "audio" / "mixed.wav"
            mixed.parent.mkdir(parents=True)
            mixed.write_bytes(b"RIFF")
            path = write_final_mix_partial_receipt(
                root,
                prior_sc="dynamic_eq",
                error="sidechain graph hang",
                mixed=mixed,
                error_type="TimeoutExpired",
                affected_tracks=["mx", "dx", "bg"],
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "final-mix-partial")
            self.assertTrue(data["partial"])
            self.assertEqual(data["reason_code"], "sidechain_mix_failed_amix_fallback")
            self.assertEqual(data["affected_tracks"], ["mx", "dx", "bg"])
            self.assertTrue(data.get("honest_limits"))
            self.assertEqual(data["error_type"], "TimeoutExpired")
            self.assertGreaterEqual(int(data["schema_version"]), 2)


class TimelineAndPostDoctorHotpathTests(unittest.TestCase):
    def test_dual_clock_detected_and_rewrite_aligns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "receipts" / "film_timeline.json",
                {"shot_starts": [0.0, 6.0, 12.0], "output_duration": 18.0},
            )
            write_json(
                root / "timeline.json",
                {
                    "shot_starts": [0.0, 7.6, 15.0],
                    "shots": [
                        {"id": "s01", "duration_sec": 7.6},
                        {"id": "s02", "duration_sec": 7.4},
                        {"id": "s03", "duration_sec": 6.0},
                    ],
                },
            )
            audit = audit_timeline_clock(root, write=True)
            self.assertTrue(audit.get("dual_clock"))
            self.assertFalse(audit.get("ok"))
            out = rewrite_timeline_from_film(root)
            self.assertTrue(out.get("ok"))
            tl = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
            self.assertEqual(tl["shot_starts"], [0.0, 6.0, 12.0])

    def test_post_doctor_hard_on_double_burn_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "receipts" / "post-route.json",
                {
                    "kind": "post-route",
                    "caption_path": "master_hf",
                    "plate_subs": "burn",
                },
            )
            report = run_post_doctor(root, write=True)
            codes = {i["code"] for i in report.get("hard") or []}
            self.assertIn("DOUBLE_BURN_RISK", codes)
            self.assertFalse(report.get("ok"))


class PlateTimeoutFloorHotpathTests(unittest.TestCase):
    def test_short_floor_and_long_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                estimate_plate_timeout(root, duration_sec=60, shot_count=8),
                1200,
            )
            self.assertGreaterEqual(
                estimate_plate_timeout(root, duration_sec=500, shot_count=20),
                1800,
            )


class QueueHonestyHotpathTests(unittest.TestCase):
    def test_run_next_queue_empty_records_open_ops_and_decision_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "film-spec.json", {"title": "hotpath-queue-empty", "scenes": []})
            with mock.patch(
                "h3_fill_idle.next_fill_idle_job",
                return_value={"ok": True, "next": None, "pending_count": 3},
            ):
                rep = run_next_fill_idle(root, execute=True, max_jobs=1)
            self.assertEqual(rep.get("skipped_reason"), "queue_empty")
            self.assertEqual(rep.get("halt_reason_code"), "RUN_QUEUE_EMPTY")
            self.assertEqual(rep.get("halt_reason_group"), "queue")
            self.assertTrue(rep.get("open_ops"))
            open_op = rep["open_ops"][0]
            self.assertEqual(open_op.get("halt_reason_code"), "RUN_QUEUE_EMPTY")
            self.assertEqual(open_op.get("halt_reason_group"), "queue")
            self.assertEqual(open_op.get("reason"), "queue_empty")
            self.assertEqual(open_op.get("pending_after"), 3)
            self.assertEqual(open_op.get("next_after"), None)
            self.assertIn("request", rep.get("decision_tree") or {})
            self.assertEqual(len(rep.get("decision_trees") or []), 1)

    def test_run_next_capacity_skip_has_machine_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "hotpath-queue",
                    "h3": {"enabled": True},
                    "genre": "adult",
                    "heat_scale": "max",
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "hero1",
                                    "shot_role": "hero",
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                    "dramatic_function": "action",
                                }
                            ]
                        }
                    ],
                },
            )
            with mock.patch(
                "h3_fill_idle.next_fill_idle_job",
                return_value={
                    "ok": True,
                    "next": {
                        "shot_id": "hero1",
                        "mode": "i2v",
                        "priority": "P0a",
                        "lane": "primary_h3",
                        "command": (
                            "aifilm h3 run --root \"X\" --shot-id hero1 --mode i2v --register"
                        ),
                    },
                    "capacity_ready": False,
                },
            ):
                rep = run_next_fill_idle(root, execute=True, max_jobs=1)
            self.assertEqual(rep.get("skipped_reason"), "capacity_not_ready")
            self.assertEqual(rep.get("halt_reason_code"), "RUN_NOT_EXECUTED_CAPACITY")
            self.assertEqual(rep.get("halt_reason_group"), "capacity")
            self.assertEqual(len(rep.get("open_ops") or []), 1)
            self.assertEqual(rep["open_ops"][0].get("halt_reason_code"), "RUN_NOT_EXECUTED_CAPACITY")
            self.assertEqual(rep["open_ops"][0].get("halt_reason_group"), "capacity")
            self.assertEqual(rep["open_ops"][0].get("reason"), "capacity_not_ready")
            self.assertIn("aifilm h3 run", rep["open_ops"][0].get("command", ""))

    def test_until_empty_execute_requires_i_own_the_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "hotpath-until-empty",
                    "h3": {"enabled": True},
                    "genre": "adult",
                    "heat_scale": "max",
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "hero1",
                                    "shot_role": "hero",
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                    "dramatic_function": "action",
                                }
                            ]
                        }
                    ],
                },
            )
            rep = fill_idle_until_empty(root, execute=True, i_own_the_gpu=False, max_cycles=1)
            self.assertFalse(rep.get("ok"))
            self.assertEqual(rep.get("stop_reason"), "exclusive_gpu_required")


class FinalHonestyHotpathTests(unittest.TestCase):
    def test_official_final_plate_blocks_final_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "receipts" / "official-final-report.json",
                {
                    "status": "OFFICIAL_FINAL_PLATE",
                    "master_lock": False,
                    "partial": True,
                },
            )
            report = plate_blocks_final_complete(root, gates={"final_complete": True})
            self.assertFalse(report.get("ok"))
            self.assertTrue(report.get("blocks_ship_complete"))
            self.assertIn("PLATE_CLAIMED_FINAL_COMPLETE", report.get("codes") or [])

    def test_official_final_visibility_defaults_for_manifest_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "receipts" / "official-final-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps({"status": "OFFICIAL_FINAL_PLATE"}),
                encoding="utf-8",
            )
            entry = build_final_film_manifest_entry(
                final_path=Path("/tmp/final.mp4"),
                output_sha256="sha256-mock",
                duration_sec=7.7,
                report_path=report_path,
                technical_qa={"ok": True},
                official_final=json.loads(report_path.read_text(encoding="utf-8")),
            )
            self.assertEqual(entry["delivery_class"], "OFFICIAL_FINAL_PLATE")
            self.assertEqual(entry["delivery_source"], "official_final_report")
            self.assertEqual(entry["delivery_visibility"], "visible_plate")
            self.assertFalse(entry["master_lock"])


if __name__ == "__main__":
    unittest.main()
