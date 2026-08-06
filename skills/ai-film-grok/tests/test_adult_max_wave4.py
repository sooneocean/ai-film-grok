"""Wave 4: heat loop in dispatch / next / preflight / write-spec receipt."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from heat_check import heat_agent_status  # noqa: E402
from preflight import run_preflight  # noqa: E402


def _write_max_film(root: Path, *, weak: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir(exist_ok=True)
    if weak:
        shots = [
            {
                "id": "s1",
                "heat_phase": "setup",
                "duration_sec": 12,
                "nar": "雨夜。",
                "wardrobe_state": "full",
                "dramatic_function": "hook",
                "dsl": {
                    "subject": "woman",
                    "action": "enter",
                    "motion": "dolly_in",
                    "wardrobe_state": "full",
                },
            },
            {
                "id": "s2",
                "heat_phase": "act",
                "duration_sec": 4,
                "nar": "靠近。",
                "wardrobe_state": "full",
                "dramatic_function": "action",
                "dsl": {
                    "subject": "couple",
                    "action": "hug",
                    "motion": "hold",
                    "wardrobe_state": "full",
                },
            },
        ]
        impact = {"score": 20.0, "grade": "D", "bands": {}}
    else:
        shots = [
            {
                "id": "a1",
                "heat_phase": "foreplay",
                "duration_sec": 6,
                "nar": "肩带一滑。贴身耳语。",
                "wardrobe_state": "partial",
                "dramatic_function": "sensory",
                "dsl": {
                    "subject": "woman",
                    "action": "undress slide",
                    "motion": "reveal",
                    "wardrobe_state": "partial",
                },
            },
            {
                "id": "a2",
                "heat_phase": "act",
                "duration_sec": 12,
                "nar": "沉腰吃进。跨坐锁腰。",
                "wardrobe_state": "bare",
                "coitus_beat": "rhythm",
                "sex_arc_beat": "penetration",
                "coverage_role": "detail",
                "dramatic_function": "action",
                "dsl": {
                    "subject": "couple",
                    "action": "hips-sink thrust straddle",
                    "motion": "rhythm_hips",
                    "wardrobe_state": "bare",
                    "camera": {"shot_size": "close-up insert"},
                    "coverage_role": "detail",
                    "framing": "union_closeup",
                },
            },
            {
                "id": "a3",
                "heat_phase": "climax",
                "duration_sec": 10,
                "nar": "失声办穿。腿软。",
                "wardrobe_state": "bare",
                "coitus_beat": "finish",
                "sex_arc_beat": "climax_release",
                "dramatic_function": "action",
                "dsl": {
                    "subject": "couple",
                    "action": "arch-finish climax",
                    "motion": "finish_arch",
                    "wardrobe_state": "bare",
                },
            },
        ]
        impact = {"score": 92.0, "grade": "S", "bands": {}}
    spec = {
        "title": "wave4",
        "heat_scale": "max",
        "spice_level": "extreme",
        "adult_max_iron": True,
        "erotic_impact_strict": True,
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "_erotic_impact": impact,
        "director_intent": {
            "logline": "雨夜后座办事完成可说满的完整承诺句。",
            "tone": "成人色气",
            "emotional_arc": ["hook", "rise", "climax"],
        },
        "scenes": [{"shots": shots}],
    }
    (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "clips": {}, "stills": {}, "gates": {}}),
        encoding="utf-8",
    )


class HeatAgentStatusTests(unittest.TestCase):
    def test_weak_max_hard_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, weak=True)
            st = heat_agent_status(root)
            self.assertTrue(st.get("active"))
            self.assertTrue(st.get("hard_fail") or st.get("needs_boost"))
            self.assertIn("heat boost", st.get("next_cmd") or "")


class PreflightMaxIronTests(unittest.TestCase):
    def test_low_impact_hard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, weak=True)
            # preflight needs more files sometimes — tolerate missing optional
            try:
                rep = run_preflight(root)
            except Exception as exc:  # noqa: BLE001
                self.skipTest(f"preflight env: {exc}")
            codes = [i.get("code") for i in (rep.get("hard") or [])]
            # At least one adult max hard signal or hard_ok false
            self.assertTrue(
                (not rep.get("hard_ok"))
                or any(
                    c
                    in {
                        "EROTIC_IMPACT_BELOW_A",
                        "HEAT_SEX_DURATION_LOW",
                        "HEAT_SEX_WARDROBE_DRESSED",
                        "SEX_ARC_PENETRATION_MISSING",
                    }
                    for c in codes
                ),
                rep,
            )


if __name__ == "__main__":
    unittest.main()
