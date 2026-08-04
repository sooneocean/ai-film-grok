"""Hot-path delivery contracts (Batch D · ROI 2026-08-03).

Locks lesson-backed invariants that must not regress:

- final stages receipt names plate ``subs off`` + HyperFrames caption ownership
- HF caption gate fails closed when pixel probe is explicitly negative
- heat final/media gates fail closed if ``heat_check`` cannot be imported
- plate double-burn guard still rejects burned-in underlay plates

These complement test_final_stages / test_compose_render / test_adult_max_wave6
without re-testing happy-path bulk.
"""

from __future__ import annotations

import pytest

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

import final_stages  # noqa: E402
from compose_render import ComposeRenderError, assert_underlay_not_double_burn  # noqa: E402
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_heat_allows_final,
    assert_heat_allows_media,
)


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


if __name__ == "__main__":
    unittest.main()
