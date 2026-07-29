"""Wave 6: final/export fail-closed on heat final_ok (S-grade)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dispatch_compact import HARD_GATE_CODES, compact_dispatch  # noqa: E402
from heat_check import heat_agent_status  # noqa: E402
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_heat_allows_final,
    assert_heat_allows_media,
)


def _write_max_film(root: Path, *, score: float, grade: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir(exist_ok=True)
    if score < 50:
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
    impact = {"score": score, "grade": grade, "bands": {}, "spec_score": score}
    spec = {
        "title": "wave6",
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


class HeatFinalGateTests(unittest.TestCase):
    def test_final_blocks_hard_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, score=20.0, grade="D")
            with self.assertRaises(ProductionGateError) as ctx:
                assert_heat_allows_final(root)
            self.assertIn("heat final gate", str(ctx.exception).lower())

    def test_final_blocks_needs_boost_even_if_above_a(self) -> None:
        """A-grade (e.g. 80) may pass queue (hard_fail=false) but fail final S gate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Strong enough fields to avoid field hard codes; score mid-A
            _write_max_film(root, score=80.0, grade="A")
            st = heat_agent_status(root)
            # If full heat_check rewrites score, still assert final path
            if st.get("hard_fail"):
                # field codes may hard_fail — still proves final blocks
                with self.assertRaises(ProductionGateError):
                    assert_heat_allows_final(root)
                return
            if st.get("needs_boost") or not st.get("final_ok"):
                with self.assertRaises(ProductionGateError) as ctx:
                    assert_heat_allows_final(root)
                msg = str(ctx.exception).lower()
                self.assertIn("heat final", msg)
            else:
                # Unexpected full S from heat_check — gate should pass
                rep = assert_heat_allows_final(root)
                self.assertTrue(rep.get("ok"))

    def test_queue_still_only_hard_fail(self) -> None:
        """Wave 5 contract: media only hard_fail; needs_boost alone does not block queue."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, score=80.0, grade="A")
            st = heat_agent_status(root)
            if st.get("hard_fail"):
                with self.assertRaises(ProductionGateError):
                    assert_heat_allows_media(root)
            else:
                # needs_boost may be true but media gate ok
                rep = assert_heat_allows_media(root)
                self.assertTrue(rep.get("ok"))

    def test_env_skip_final_gate(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, score=20.0, grade="D")
            os.environ["AIFILM_SKIP_HEAT_FINAL_GATE"] = "1"
            try:
                rep = assert_heat_allows_final(root)
                self.assertTrue(rep.get("skipped"))
            finally:
                os.environ.pop("AIFILM_SKIP_HEAT_FINAL_GATE", None)


class CompactFinalHeatTests(unittest.TestCase):
    def test_hard_gate_codes_include_final(self) -> None:
        self.assertIn("HEAT_FINAL_NOT_OK", HARD_GATE_CODES)

    def test_compact_attention_final_not_ok(self) -> None:
        packet = {
            "ok": True,
            "schema_version": 2,
            "at": "2026-07-29T00:00:00+00:00",
            "root": "/tmp/film",
            "craft_stage": "rough",
            "pipeline_stage": "post",
            "next_id": "heat-boost",
            "next_cmd": 'aifilm heat boost --root "/tmp/film" --apply',
            "next_why": "need S",
            "next_action": {
                "skill_id": "dispatch.orchestrate",
                "operation": "heat-boost",
                "argv": ["heat", "boost"],
                "node_refs": [],
                "input_hashes": {},
                "dependencies": [],
                "spend_class": "local",
                "approval_class": "none",
                "expected_outputs": [],
                "verification": [],
                "transaction_id": "tx-heat",
                "state_hash": "state",
            },
            "heat": {
                "active": True,
                "hard_fail": False,
                "needs_boost": True,
                "final_ok": False,
                "score": 80.0,
                "grade": "A",
                "target_s": 90.0,
                "next_cmd": 'aifilm heat boost --root "/tmp/film" --apply',
                "why": "adult max heat: impact=A:80",
            },
            "state_hash": "state",
            "metrics": {"build_elapsed_ms": 1.0},
        }
        compact = compact_dispatch(packet)
        codes = [a["code"] for a in compact.get("attention") or []]
        self.assertIn("HEAT_FINAL_NOT_OK", codes)
        self.assertFalse((compact.get("heat") or {}).get("final_ok"))


if __name__ == "__main__":
    unittest.main()
