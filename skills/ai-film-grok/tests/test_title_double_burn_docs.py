"""Structural checks: title double-burn sediment stays wired into skill defaults."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSON = ROOT / "references" / "lessons-2026-07-20-title-double-burn.md"
SKILL = ROOT / "SKILL.md"
POST_COMPOSE = ROOT / "references" / "post-compose.md"
POSTPROD = ROOT / "references" / "postproduction.md"
DISC = ROOT / "references" / "production-discipline.md"
EXPORT = ROOT / "scripts" / "export_composition.py"
RENDER = ROOT / "scripts" / "render_final.py"
AIFILM = ROOT / "scripts" / "aifilm_grok.py"


class TitleDoubleBurnDocsTests(unittest.TestCase):
    def test_lesson_exists_with_p5_and_defaults(self) -> None:
        self.assertTrue(LESSON.is_file(), f"missing {LESSON}")
        text = LESSON.read_text(encoding="utf-8")
        for needle in (
            "P5",
            "plate-cards blank",
            "subs off",
            "双烧",
            "xixifu-playful-night",
            "效果很好",
            "white-space: nowrap",
        ):
            self.assertIn(needle, text, f"missing {needle!r} in lesson")

    def test_skill_and_refs_point_to_lesson(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("lessons-2026-07-20-title-double-burn.md", skill)
        self.assertIn("plate-cards blank", skill)
        for path in (POST_COMPOSE, POSTPROD, DISC):
            body = path.read_text(encoding="utf-8")
            self.assertIn("plate-cards blank", body, f"missing plate-cards in {path.name}")
            self.assertIn("title-double-burn", body, f"missing lesson link in {path.name}")

    def test_export_css_has_nowrap(self) -> None:
        text = EXPORT.read_text(encoding="utf-8")
        self.assertIn("white-space: nowrap", text)

    def test_render_final_plate_cards_flag(self) -> None:
        text = RENDER.read_text(encoding="utf-8")
        self.assertIn("--plate-cards", text)
        self.assertIn("blank", text)
        # empty text → no glyph path
        self.assertIn("if label:", text)

    def test_aifilm_defaults_blank_for_designed_post(self) -> None:
        text = AIFILM.read_text(encoding="utf-8")
        self.assertIn("plate_cards", text)
        # default branch: designed-post → blank
        self.assertIn('"blank" if post_engine in {"hyperframes", "remotion"}', text)
        self.assertIn("--plate-cards", text)


if __name__ == "__main__":
    unittest.main()
