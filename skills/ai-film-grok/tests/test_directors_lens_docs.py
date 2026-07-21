"""Structural checks: Director's Lens narrative upstream stays wired into skill."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENS = ROOT / "references" / "directors-lens.md"
LESSON = ROOT / "references" / "lessons-2026-07-20-directors-lens.md"
SKILL = ROOT / "SKILL.md"
FILM_SPEC_MD = ROOT / "references" / "film-spec.md"
PRINCIPLES = ROOT / "references" / "principles.md"
SHOT_MOTION = ROOT / "references" / "shot-motion.md"
EXAMPLE_JSON = ROOT / "templates" / "film-spec.example.json"
EXAMPLE_MD = ROOT / "templates" / "directors-lens.example.md"


class DirectorsLensDocsTests(unittest.TestCase):
    def test_core_docs_exist(self) -> None:
        for path in (LENS, LESSON, EXAMPLE_MD):
            self.assertTrue(path.is_file(), f"missing {path}")

    def test_lens_has_phases_and_mapping(self) -> None:
        text = LENS.read_text(encoding="utf-8")
        for needle in (
            "Director’s Lens",
            "Show, don’t tell",
            "Phase A",
            "Phase B",
            "Phase C",
            "visible_change",
            "dramatic_function",
            "film-spec",
            "transition_intents",
            "extreme close-up",
            "receipts/directors-lens.md",
            "P0",
            "P4",
        ):
            self.assertIn(needle, text, f"missing {needle!r} in directors-lens.md")

    def test_skill_wires_lens_upstream(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("directors-lens.md", skill)
        self.assertIn("lessons-2026-07-20-directors-lens.md", skill)
        self.assertIn("先 Director’s Lens", skill)
        # Main spine keeps Agent 区简写；Lens 细节在 references 表
        self.assertTrue(
            "### 0. Director’s Lens" in skill
            or "Directors Lens" in skill
            or "directors-lens.md" in skill
        )
        self.assertIn("插图化", skill)

    def test_refs_point_to_lens(self) -> None:
        for path in (FILM_SPEC_MD, PRINCIPLES, SHOT_MOTION, LESSON):
            body = path.read_text(encoding="utf-8")
            self.assertIn("directors-lens", body, f"missing directors-lens link in {path.name}")

    def test_example_json_has_lens_optional_fields(self) -> None:
        data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
        intent = data["director_intent"]
        for key in ("theme", "act_structure", "pace_chart", "visual_motifs"):
            self.assertIn(key, intent, f"film-spec.example missing director_intent.{key}")
        self.assertIn("setup", intent["act_structure"])

    def test_example_md_has_shot_table(self) -> None:
        text = EXAMPLE_MD.read_text(encoding="utf-8")
        self.assertIn("shot01", text)
        self.assertIn("visible_change", text)
        self.assertIn("Phase A", text)


if __name__ == "__main__":
    unittest.main()
