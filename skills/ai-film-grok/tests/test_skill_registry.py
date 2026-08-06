#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from skill_registry import list_skills, load_registry, show_skill, skill_ids  # noqa: E402


class SkillRegistryTests(unittest.TestCase):
    def test_load_and_list(self) -> None:
        reg = load_registry()
        self.assertTrue(reg.get("ok"), reg)
        self.assertGreaterEqual(len(reg.get("skills") or []), 10)
        listed = list_skills()
        self.assertTrue(listed.get("ok"))
        self.assertGreaterEqual(listed.get("count") or 0, 10)
        ids = skill_ids()
        self.assertIn("image.animate", ids)
        self.assertIn("dispatch.orchestrate", ids)
        self.assertIn("shot.plan", ids)

    def test_show_image_animate(self) -> None:
        report = show_skill("image.animate")
        self.assertTrue(report.get("ok"), report)
        skill = report.get("skill") or {}
        self.assertEqual(skill.get("id"), "image.animate")
        self.assertIn("MotionClip", skill.get("produces") or [])

    def test_show_unknown(self) -> None:
        report = show_skill("no.such.skill")
        self.assertFalse(report.get("ok"))

    def test_filter_tag(self) -> None:
        listed = list_skills(tag="audio")
        self.assertTrue(listed.get("ok"))
        for s in listed.get("skills") or []:
            self.assertIn("audio", s.get("tags") or [])


if __name__ == "__main__":
    unittest.main()
