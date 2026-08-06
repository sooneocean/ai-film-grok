"""Wave 5: media-queue fail-closed on heat hard_fail; craft/compact heat surface."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from craft_spine import craft_status_report, detect_craft_stage  # noqa: E402
from dispatch_compact import HARD_GATE_CODES, compact_dispatch  # noqa: E402
from heat_check import heat_agent_status  # noqa: E402
from media_queue import MediaQueue, QueueError  # noqa: E402
from production_gates import ProductionGateError, assert_heat_allows_media  # noqa: E402


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
        impact = {"score": 20.0, "grade": "D", "bands": {}, "spec_score": 20.0}
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
        impact = {"score": 92.0, "grade": "S", "bands": {}, "spec_score": 92.0}
    spec = {
        "title": "wave5",
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


class HeatQueueGateTests(unittest.TestCase):
    def test_assert_heat_blocks_weak_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, weak=True)
            st = heat_agent_status(root)
            self.assertTrue(st.get("hard_fail") or st.get("needs_boost"))
            with self.assertRaises(ProductionGateError) as ctx:
                assert_heat_allows_media(root)
            self.assertIn("heat queue gate", str(ctx.exception).lower())

    def test_assert_heat_skips_non_adult(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            (root / "film-spec.json").write_text(
                json.dumps({"title": "soft", "heat_scale": "soft", "scenes": [{"shots": []}]}),
                encoding="utf-8",
            )
            rep = assert_heat_allows_media(root)
            self.assertTrue(rep.get("ok") or not rep.get("active", True))

    def test_media_queue_add_blocked_on_hard_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, weak=True)
            prompt = root / "prompt.txt"
            frame = root / "frame.png"
            prompt.write_text("p", encoding="utf-8")
            frame.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
            # image_edit: skip anatomy I2V gate so heat queue gate is reachable
            queue = MediaQueue(root, budget_units=20)
            with self.assertRaises(QueueError) as ctx:
                queue.add_job(
                    shot_id="s1",
                    operation="image_edit",
                    prompt_file=prompt,
                    inputs=[frame],
                    allow_without_pilot=True,
                )
            msg = str(ctx.exception).lower()
            self.assertTrue("heat" in msg or "scale" in msg or "impact" in msg, msg)

    def test_env_skip_heat_queue_gate(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, weak=True)
            os.environ["AIFILM_SKIP_HEAT_QUEUE_GATE"] = "1"
            try:
                rep = assert_heat_allows_media(root)
                self.assertTrue(rep.get("skipped"))
            finally:
                os.environ.pop("AIFILM_SKIP_HEAT_QUEUE_GATE", None)


class CraftHeatSurfaceTests(unittest.TestCase):
    def test_craft_blocker_on_weak_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_max_film(root, weak=True)
            craft = detect_craft_stage(root)
            heat = craft.get("heat") or {}
            self.assertTrue(heat.get("active"))
            self.assertTrue(
                heat.get("hard_fail") or heat.get("needs_boost"),
                heat,
            )
            blockers = craft.get("blockers") or []
            self.assertTrue(
                "heat_agent_hard_fail" in blockers or "heat_needs_boost" in blockers,
                blockers,
            )
            rep = craft_status_report(root)
            self.assertIn("heat", (rep.get("next_hint") or "").lower())


class CompactHeatSurfaceTests(unittest.TestCase):
    def test_hard_gate_code_listed(self) -> None:
        self.assertIn("HEAT_AGENT_HARD_FAIL", HARD_GATE_CODES)

    def test_compact_attention_heat_hard_fail(self) -> None:
        packet = {
            "ok": True,
            "schema_version": 2,
            "at": "2026-07-29T00:00:00+00:00",
            "root": "/tmp/film",
            "craft_stage": "media",
            "pipeline_stage": "visual",
            "next_id": "heat-boost",
            "next_cmd": 'aifilm heat boost --root "/tmp/film" --apply',
            "next_why": "HARD adult max",
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
                "hard_fail": True,
                "needs_boost": True,
                "score": 20.0,
                "grade": "D",
                "ecchi_score": 1,
                "next_cmd": 'aifilm heat boost --root "/tmp/film" --apply',
                "why": "HARD adult max heat: impact=D:20",
            },
            "state_hash": "state",
            "metrics": {"build_elapsed_ms": 1.0},
        }
        compact = compact_dispatch(packet)
        codes = [a["code"] for a in compact.get("attention") or []]
        self.assertIn("HEAT_AGENT_HARD_FAIL", codes)
        self.assertTrue((compact.get("heat") or {}).get("hard_fail"))
        self.assertEqual(compact["metrics"].get("heat_hard_fail"), True)
        self.assertIn("HEAT_AGENT_HARD_FAIL", compact.get("hard_gate_codes") or [])


if __name__ == "__main__":
    unittest.main()
