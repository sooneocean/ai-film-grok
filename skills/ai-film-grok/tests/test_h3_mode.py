"""H3 max-effect mode selection (I2V / R2V / T2V)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from h3_mode import resolve_h3_mode
from h3_workflow import list_h3_eligible_shots, plan_h3_shot
from util import write_json


def _shot(**kwargs):
    base = {
        "id": "s1",
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "bare",
        "dramatic_function": "action",
    }
    base.update(kwargs)
    return base


class ResolveH3ModeTests(unittest.TestCase):
    def test_explicit_mode_wins(self) -> None:
        r = resolve_h3_mode(_shot(h3_mode="t2v"), has_still=True)
        self.assertEqual(r["mode"], "t2v")

    def test_continue_forces_i2v(self) -> None:
        r2 = resolve_h3_mode(_shot(force_r2v=True), has_still=True, wants_continue=True)
        self.assertEqual(r2["mode"], "i2v")

    def test_env_is_t2v(self) -> None:
        r = resolve_h3_mode(
            _shot(shot_role="env", heat_phase="setup", wardrobe_state="clothed"),
            intent={"shot_role": "env", "content_class": "general"},
            has_still=False,
        )
        self.assertEqual(r["mode"], "t2v")

    def test_default_hero_still_is_i2v(self) -> None:
        r = resolve_h3_mode(_shot(), has_still=True)
        self.assertEqual(r["mode"], "i2v")

    def test_dialogue_close_restricted_is_i2v_with_combo_winners(self) -> None:
        """combo winners dialogue_mouth_energy → I2V primary (R2V alt for extreme mouth)."""
        r = resolve_h3_mode(
            _shot(
                shot_size="cu",
                screen_mode="on_camera",
                audio_cues=[{"spoken_text": "别停", "screen_mode": "on_camera"}],
            ),
            intent={
                "content_class": "restricted_local",
                "shot_role": "hero",
                "spoken_text": "别停",
                "screen_mode": "on_camera",
                "motion_tier": "high",
            },
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["mode"], "i2v")
        self.assertEqual(r.get("combo_lane"), "dialogue_mouth_energy")
        self.assertEqual(r.get("combo_preferred_mode"), "i2v")
        self.assertIn("combo_win_dialogue_i2v", r.get("reasons") or [])
        self.assertEqual(r.get("alt_mode"), "r2v")


    def test_dialogue_close_with_last_prefers_flf(self) -> None:
        r = resolve_h3_mode(
            _shot(
                shot_size="cu",
                screen_mode="on_camera",
                audio_cues=[{"spoken_text": "别停", "screen_mode": "on_camera"}],
            ),
            intent={
                "content_class": "restricted_local",
                "shot_role": "hero",
                "spoken_text": "别停",
                "screen_mode": "on_camera",
                "motion_tier": "high",
            },
            has_still=True,
            has_last=True,
        )
        self.assertEqual(r["mode"], "flf")
        self.assertEqual(r["alt_mode"], "r2v")
        self.assertIn("first_last_primary", r["reasons"])

    def test_high_motion_difficulty_is_r2v_without_last(self) -> None:
        r = resolve_h3_mode(
            _shot(),
            intent={
                "content_class": "restricted_local",
                "shot_role": "hero",
                "heat_phase": "act",
                "motion_tier": "high",
                "difficulty_flags": ["coitus_beat:deep_thrust", "sex_pose:missionary"],
            },
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["mode"], "r2v")

    def test_high_motion_with_last_prefers_flf(self) -> None:
        r = resolve_h3_mode(
            _shot(),
            intent={
                "content_class": "restricted_local",
                "shot_role": "hero",
                "heat_phase": "act",
                "motion_tier": "high",
                "difficulty_flags": ["coitus_beat:deep_thrust", "sex_pose:missionary"],
            },
            has_still=True,
            has_last=True,
        )
        self.assertEqual(r["mode"], "flf")
        self.assertEqual(r["alt_mode"], "r2v")

    def test_soft_high_motion_keeps_i2v_with_r2v_alt(self) -> None:
        r = resolve_h3_mode(
            _shot(),
            intent={
                "content_class": "restricted_local",
                "shot_role": "hero",
                "heat_phase": "act",
                "motion_tier": "high",
                "difficulty_flags": [],
            },
            has_still=True,
        )
        self.assertEqual(r["mode"], "i2v")
        self.assertEqual(r["alt_mode"], "r2v")

    def test_force_r2v_flag(self) -> None:
        r = resolve_h3_mode(_shot(force_r2v=True), has_still=True)
        self.assertEqual(r["mode"], "r2v")

    def test_combo_lane_annotation_on_env(self) -> None:
        r = resolve_h3_mode(
            _shot(shot_role="env", heat_phase="setup", wardrobe_state="clothed"),
            intent={"shot_role": "env", "content_class": "general"},
            has_still=False,
        )
        self.assertEqual(r["mode"], "t2v")
        self.assertEqual(r.get("combo_lane"), "faceless_env")
        self.assertEqual(r.get("combo_preferred_mode"), "t2v")


class PlanListH3ModeTests(unittest.TestCase):
    def _film(self, root: Path, shots: list) -> None:
        write_json(
            root / "film-spec.json",
            {
                "title": "h3-mode-test",
                "h3": {"enabled": True},
                "genre": "adult",
                "heat_scale": "max",
                "director_intent": {"protagonist_want": "survive"},
                "scenes": [{"shots": shots}],
            },
        )

    def test_plan_surfaces_mode_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stills").mkdir()
            (root / "stills" / "m1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            self._film(
                root,
                [
                    {
                        "id": "m1",
                        "shot_role": "hero",
                        "heat_phase": "act",
                        "wardrobe_state": "bare",
                        "dramatic_function": "action",
                        "shot_size": "ecu",
                        "screen_mode": "on_camera",
                        "audio_cues": [{"spoken_text": "快点", "screen_mode": "on_camera"}],
                    }
                ],
            )
            plan = plan_h3_shot(root, "m1")
            self.assertEqual(plan["mode"], "i2v")
            self.assertIn("mode_resolve", plan)
            self.assertEqual(plan["mode_resolve"].get("combo_lane"), "dialogue_mouth_energy")
            self.assertEqual(plan["mode_resolve"].get("combo_preferred_mode"), "i2v")
            self.assertEqual(
                plan.get("combo_prompt_family") or plan["mode_resolve"].get("combo_prompt_family"),
                "dialogue_mouth_max",
            )
            self.assertTrue(plan.get("effect_tips"))

    def test_list_includes_mode_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stills").mkdir()
            (root / "stills" / "a1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            self._film(
                root,
                [
                    {
                        "id": "a1",
                        "shot_role": "hero",
                        "heat_phase": "act",
                        "wardrobe_state": "bare",
                        "dramatic_function": "action",
                    }
                ],
            )
            report = list_h3_eligible_shots(root)
            self.assertTrue(report["ok"])
            meat = report["shots"][0]
            self.assertIn(meat["mode"], {"i2v", "r2v"})
            self.assertIn("--mode", meat["command"])
            self.assertIn("h3_max_effect_v1", str(report.get("policy") or ""))


if __name__ == "__main__":
    unittest.main()
