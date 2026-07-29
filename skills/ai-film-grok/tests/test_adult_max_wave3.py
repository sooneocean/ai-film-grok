"""Wave 3: impact S boost, ecchi checklist, mute-frame advisory."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    apply_impact_boost_patches,
    lint_ecchi_checklist,
    suggest_impact_boost_actions,
)
from heat_check import heat_boost, mute_frame_advisory  # noqa: E402


def _weak_shots() -> list[dict]:
    return [
        {
            "id": "s1",
            "heat_phase": "setup",
            "duration_sec": 10,
            "nar": "雨夜。",
            "wardrobe_state": "full",
            "dsl": {"action": "enter car", "wardrobe_state": "full"},
        },
        {
            "id": "s2",
            "heat_phase": "act",
            "duration_sec": 5,
            "nar": "靠近。",
            "wardrobe_state": "partial",
            "dsl": {"action": "hug soft", "wardrobe_state": "partial"},
        },
        {
            "id": "s3",
            "heat_phase": "climax",
            "duration_sec": 4,
            "nar": "灯暗。",
            "wardrobe_state": "partial",
            "dsl": {"action": "lean in", "wardrobe_state": "partial"},
        },
    ]


class EcchiChecklistTests(unittest.TestCase):
    def test_thin_max_flags(self) -> None:
        rep = lint_ecchi_checklist(_weak_shots(), heat_scale="max")
        self.assertTrue(rep.get("enabled"))
        self.assertIn("ECCHI_CHECKLIST_THIN", rep.get("codes") or [])
        self.assertLess(rep.get("score", 0), 6)

    def test_full_max_ok(self) -> None:
        shots = [
            {
                "id": "a",
                "heat_phase": "foreplay",
                "nar": "她把你按近耳语，肩带一滑，热潮喘。",
                "wardrobe_state": "partial",
                "dsl": {"action": "close straddle undress"},
            },
            {
                "id": "b",
                "heat_phase": "act",
                "nar": "落锁规矩作废。沉腰吃进，跨坐锁腰。",
                "wardrobe_state": "bare",
                "dsl": {"action": "hips-sink thrust straddle"},
            },
            {
                "id": "c",
                "heat_phase": "climax",
                "nar": "失声办穿。腿软，下一场换你顶。",
                "wardrobe_state": "bare",
                "dsl": {"action": "arch-finish climax"},
            },
        ]
        rep = lint_ecchi_checklist(shots, heat_scale="max")
        self.assertTrue(rep.get("ok"), rep)
        self.assertGreaterEqual(rep.get("score"), 6)


class ImpactBoostTests(unittest.TestCase):
    def test_suggest_has_actions(self) -> None:
        plan = suggest_impact_boost_actions(_weak_shots(), heat_scale="max", target_score=90)
        self.assertTrue(plan.get("needed"))
        kinds = {a["kind"] for a in plan.get("actions") or []}
        self.assertTrue(kinds & {"lengthen_meat", "set_bare_peak", "add_detail_cu", "penetration_verbs"})

    def test_apply_patches_raises_fields(self) -> None:
        shots = _weak_shots()
        plan = suggest_impact_boost_actions(shots, heat_scale="max", target_score=90)
        out = apply_impact_boost_patches(shots, list(plan.get("actions") or []))
        self.assertGreater(out.get("changed", 0), 0)
        climax = next(s for s in shots if s["heat_phase"] == "climax")
        self.assertEqual(climax.get("wardrobe_state"), "bare")
        act = next(s for s in shots if s["heat_phase"] == "act")
        self.assertTrue(
            act.get("coverage_role") == "detail"
            or "hips-sink" in str((act.get("dsl") or {}).get("action") or "")
            or float(act.get("duration_sec") or 0) > 5
        )


class MuteFrameAdvisoryTests(unittest.TestCase):
    def test_lists_meat_shots(self) -> None:
        adv = mute_frame_advisory(_weak_shots(), heat_scale="max")
        self.assertTrue(adv.get("enabled"))
        ids = {x["shot_id"] for x in adv.get("shots") or []}
        self.assertIn("s2", ids)
        self.assertIn("s3", ids)
        self.assertNotIn("s1", ids)


class HeatBoostCliPathTests(unittest.TestCase):
    def test_boost_apply_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            spec = {
                "title": "boost-test",
                "heat_scale": "max",
                "spice_level": "extreme",
                "scenes": [{"shots": _weak_shots()}],
            }
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            rep = heat_boost(root, apply=True, target_score=90)
            self.assertTrue(rep.get("ok"), rep)
            self.assertTrue((root / "receipts" / "heat-boost.json").is_file())
            updated = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            shots = updated["scenes"][0]["shots"]
            self.assertTrue(any(s.get("wardrobe_state") == "bare" for s in shots))


if __name__ == "__main__":
    unittest.main()
