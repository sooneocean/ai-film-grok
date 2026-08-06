"""Wave 2 adult max: duration rebalance, promote wardrobe, music energy, soften-compensate, pilot beats."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity_chain import promote_wardrobe_ok, should_auto_promote_next  # noqa: E402
from production_gates import ProductionGateError, assert_pilot_user_approved  # noqa: E402
from sound_plan import inject_music_energy_spotting  # noqa: E402
from story_plan import (  # noqa: E402
    _compact_adult_spine_for_scene,
    rebalance_adult_beat_durations,
)


class DurationRebalanceTests(unittest.TestCase):
    def test_rebalance_lifts_meat_share(self) -> None:
        beats = [
            {"heat_phase": "setup", "targetDuration": 20.0},
            {"heat_phase": "foreplay", "targetDuration": 10.0},
            {"heat_phase": "act", "coitus_beat": "rhythm", "targetDuration": 8.0},
            {"heat_phase": "climax", "coitus_beat": "finish", "targetDuration": 4.0},
            {"heat_phase": "afterglow", "targetDuration": 8.0},
        ]
        out = rebalance_adult_beat_durations(beats, scene_budget_sec=50.0, sex_floor=0.50)
        total = sum(float(b["targetDuration"]) for b in out)
        meat = sum(float(b["targetDuration"]) for b in out if b["heat_phase"] in {"act", "climax"})
        self.assertGreaterEqual(meat / total, 0.50 - 1e-6)

    def test_compact_sex_scene_has_climax_bare(self) -> None:
        spine = _compact_adult_spine_for_scene("两人沉腰办事卸装缠绵")
        phases = [b.get("heat_phase") for b in spine]
        self.assertIn("act", phases)
        self.assertIn("climax", phases)
        bare = [b for b in spine if b.get("wardrobe_state") == "bare"]
        self.assertTrue(bare)


class PromoteWardrobeTests(unittest.TestCase):
    def test_redress_blocked_on_max(self) -> None:
        prev = {"wardrobe_state": "bare", "dsl": {"chain_mode": "continue"}}
        nxt = {"wardrobe_state": "full", "dsl": {"chain_mode": "continue"}}
        ok, why = promote_wardrobe_ok(prev, nxt, heat_scale="max")
        self.assertFalse(ok)
        self.assertIn("RE_DRESS", why)
        do, reason = should_auto_promote_next(prev, nxt, heat_scale="max")
        self.assertFalse(do)
        self.assertIn("RE_DRESS", reason)

    def test_escalate_undress_ok(self) -> None:
        prev = {"wardrobe_state": "partial", "dsl": {"chain_mode": "continue"}}
        nxt = {"wardrobe_state": "bare", "dsl": {"chain_mode": "continue"}}
        ok, _ = promote_wardrobe_ok(prev, nxt, heat_scale="max")
        self.assertTrue(ok)
        do, _ = should_auto_promote_next(prev, nxt, heat_scale="max")
        self.assertTrue(do)


class MusicEnergyTests(unittest.TestCase):
    def test_inject_spotting_by_phase(self) -> None:
        plan = {"mood": "rnb", "events": []}
        shots = [
            {"id": "s1", "heat_phase": "setup"},
            {"id": "s2", "heat_phase": "act"},
            {"id": "s3", "heat_phase": "climax"},
        ]
        out = inject_music_energy_spotting(plan, shots, heat_scale="max")
        assert out is not None
        spotting = out.get("music_spotting") or []
        self.assertEqual(len(spotting), 3)
        by_id = {r["shot_id"]: r for r in spotting}
        self.assertLess(by_id["s1"]["energy"], by_id["s2"]["energy"])
        self.assertLess(by_id["s2"]["energy"], by_id["s3"]["energy"])
        self.assertAlmostEqual(by_id["s3"]["energy"], 1.0)


class SoftenCompensateTests(unittest.TestCase):
    def test_apply_vo_and_sfx(self) -> None:
        from heat_check import heat_soften_compensate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            spec = {
                "title": "soft-test",
                "heat_scale": "max",
                "spice_level": "extreme",
                "vo_mode": "storyteller",
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "a1",
                                "heat_phase": "act",
                                "coitus_beat": "rhythm",
                                "nar": "灯暗了。",
                                "duration_sec": 8,
                                "dsl": {"action": "hips-sink", "wardrobe_state": "bare"},
                                "wardrobe_state": "bare",
                            },
                            {
                                "id": "c1",
                                "heat_phase": "climax",
                                "coitus_beat": "finish",
                                "nar": "夜色。",
                                "duration_sec": 6,
                                "dsl": {"action": "arch-finish", "wardrobe_state": "bare"},
                                "wardrobe_state": "bare",
                            },
                        ]
                    }
                ],
            }
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            rep = heat_soften_compensate(root, note="test soften", apply=True)
            self.assertTrue(rep.get("ok"), rep)
            updated = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            nars = [sh["nar"] for sc in updated["scenes"] for sh in sc["shots"]]
            self.assertTrue(any("沉腰" in n or "吃进" in n or "办穿" in n for n in nars), nars)
            self.assertEqual(updated.get("heat_scale"), "max")
            sp = updated.get("sound_plan") or {}
            self.assertTrue(sp.get("music_spotting") or sp.get("events"))


class PilotThreeBeatTests(unittest.TestCase):
    def test_hook_only_pilot_rejected_on_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "receipts"
            rec.mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "heat_scale": "max",
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "h1",
                                        "heat_phase": "setup",
                                        "coitus_beat": "entry",
                                    },
                                    {
                                        "id": "u1",
                                        "heat_phase": "act",
                                        "coitus_beat": "union",
                                    },
                                    {
                                        "id": "r1",
                                        "heat_phase": "act",
                                        "coitus_beat": "rhythm",
                                    },
                                    {
                                        "id": "d1",
                                        "heat_phase": "foreplay",
                                        "coitus_beat": "undress",
                                    },
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (rec / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "pilot 过",
                        "shots": ["h1"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProductionGateError, "undress|union|rhythm|adult max"):
                assert_pilot_user_approved(root, env_skip=False)

    def test_three_beat_pilot_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "receipts"
            rec.mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "heat_scale": "max",
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "d1",
                                        "heat_phase": "foreplay",
                                        "coitus_beat": "undress",
                                    },
                                    {
                                        "id": "u1",
                                        "heat_phase": "act",
                                        "coitus_beat": "union",
                                    },
                                    {
                                        "id": "r1",
                                        "heat_phase": "act",
                                        "coitus_beat": "rhythm",
                                    },
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (rec / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "pilot 过",
                        "shots": ["d1", "u1", "r1"],
                    }
                ),
                encoding="utf-8",
            )
            out = assert_pilot_user_approved(root, env_skip=False)
            self.assertTrue(out.get("ok"))


if __name__ == "__main__":
    unittest.main()
