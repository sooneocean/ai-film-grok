"""Optimization round 3 · A1 preflight bare except:pass → soft/hard issues."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _minimal_root(
    *,
    heat_scale: str = "max",
    adult_max_iron: bool = True,
    extra_spec: dict | None = None,
) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "receipts").mkdir()
    spec: dict = {
        "title": "a1-preflight-pass",
        "heat_scale": heat_scale,
        "adult_max_iron": adult_max_iron,
        "scenes": [
            {
                "shots": [
                    {"id": "s1", "heat_phase": "act", "duration_sec": 5, "nar": "短"},
                    {"id": "s2", "heat_phase": "climax", "duration_sec": 5, "nar": "短"},
                ]
            }
        ],
    }
    if extra_spec:
        spec.update(extra_spec)
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"gates": {}, "clips": {}, "stills": {}}),
        encoding="utf-8",
    )
    return root


class TestHeatArcProbeHardOnMax(unittest.TestCase):
    def test_heat_probe_error_hard_when_max_iron(self) -> None:
        from preflight import run_preflight

        root = _minimal_root(heat_scale="max", adult_max_iron=True)
        with mock.patch(
            "edit_policy.lint_heat_arc",
            side_effect=RuntimeError("heat boom"),
        ):
            rep = run_preflight(root)
        hard_codes = {
            str(i.get("code"))
            for i in (rep.get("hard") or [])
            if isinstance(i, dict)
        }
        self.assertIn(
            "heat_arc_probe_error",
            hard_codes,
            msg=f"hard={hard_codes} soft={[i.get('code') for i in (rep.get('soft') or [])][:20]}",
        )

    def test_heat_probe_error_soft_when_not_max(self) -> None:
        from preflight import run_preflight

        root = _minimal_root(heat_scale="mild", adult_max_iron=True)
        with mock.patch(
            "edit_policy.lint_heat_arc",
            side_effect=RuntimeError("heat boom mild"),
        ):
            rep = run_preflight(root)
        hard_codes = {
            str(i.get("code"))
            for i in (rep.get("hard") or [])
            if isinstance(i, dict)
        }
        soft_codes = {
            str(i.get("code"))
            for i in (rep.get("soft") or [])
            if isinstance(i, dict)
        }
        self.assertNotIn("heat_arc_probe_error", hard_codes)
        self.assertIn("heat_arc_probe_error", soft_codes)


class TestVoDragAndEqualSlotProbeSoft(unittest.TestCase):
    def test_vo_drag_probe_records_soft(self) -> None:
        from preflight import run_preflight

        root = _minimal_root(heat_scale="mild")
        # Force VO drag block to explode via default_visual_fit
        with mock.patch(
            "edit_policy.default_visual_fit",
            side_effect=RuntimeError("fit boom"),
        ):
            # equal-slot also imports default_visual_fit — ok either code
            rep = run_preflight(root)
        soft_codes = {
            str(i.get("code"))
            for i in (rep.get("soft") or [])
            if isinstance(i, dict)
        }
        self.assertTrue(
            {"vo_drag_probe_error", "equal_slot_ppt_probe_error"} & soft_codes,
            msg=f"expected vo_drag or equal_slot probe soft; got {soft_codes}",
        )

    def test_equal_slot_ppt_probe_soft(self) -> None:
        from preflight import run_preflight

        root = _minimal_root(heat_scale="mild")
        with mock.patch(
            "edit_policy.lint_equal_duration_ppt",
            side_effect=RuntimeError("ppt boom"),
        ):
            rep = run_preflight(root)
        soft_codes = {
            str(i.get("code"))
            for i in (rep.get("soft") or [])
            if isinstance(i, dict)
        }
        self.assertIn("equal_slot_ppt_probe_error", soft_codes)


class TestStanceProbeSoft(unittest.TestCase):
    def test_stance_probe_error_soft(self) -> None:
        from preflight import run_preflight

        root = _minimal_root(heat_scale="mild")
        with mock.patch(
            "edit_policy.lint_character_stance",
            side_effect=RuntimeError("stance boom"),
        ):
            rep = run_preflight(root)
        soft_codes = {
            str(i.get("code"))
            for i in (rep.get("soft") or [])
            if isinstance(i, dict)
        }
        self.assertIn("character_stance_probe_error", soft_codes)


class TestLoopRiskProbeSoft(unittest.TestCase):
    def test_loop_risk_probe_not_silent(self) -> None:
        from preflight import run_preflight

        root = _minimal_root(heat_scale="mild")
        with mock.patch(
            "preflight.loop_risk_shots_from_spec",
            side_effect=RuntimeError("loop boom"),
        ):
            rep = run_preflight(root)
        soft_codes = {
            str(i.get("code"))
            for i in (rep.get("soft") or [])
            if isinstance(i, dict)
        }
        self.assertIn("loop_risk_probe_error", soft_codes)


class TestHelpers(unittest.TestCase):
    def test_is_heat_max_iron(self) -> None:
        from preflight import _is_heat_max_iron

        self.assertTrue(_is_heat_max_iron({"heat_scale": "max"}))
        self.assertTrue(_is_heat_max_iron({"heat_scale": "hot"}))
        self.assertFalse(_is_heat_max_iron({"heat_scale": "max", "adult_max_iron": False}))
        self.assertFalse(_is_heat_max_iron({"heat_scale": "mild"}))

    def test_append_probe_error_hard_soft(self) -> None:
        from preflight import _append_probe_error

        hard: list = []
        soft: list = []
        _append_probe_error(hard, soft, code="x_probe_error", exc=RuntimeError("e"), hard_mode=True)
        _append_probe_error(hard, soft, code="y_probe_error", exc=RuntimeError("e2"), hard_mode=False)
        self.assertEqual(hard[0]["level"], "hard")
        self.assertEqual(soft[0]["level"], "soft")
        self.assertEqual(hard[0]["code"], "x_probe_error")


if __name__ == "__main__":
    unittest.main()
