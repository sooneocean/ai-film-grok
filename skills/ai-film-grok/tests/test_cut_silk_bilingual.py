"""Cut silk fluency + bilingual captions structural/unit tests."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CutSilkBilingualDocsTests(unittest.TestCase):
    def test_docs_exist(self) -> None:
        for name in (
            "references/lessons-2026-07-20-cut-silk-bilingual.md",
            "references/hf-remotion-capability-matrix.md",
            "references/lessons-2026-07-20-transition-motion-v2.md",
            "references/lessons-2026-07-20-seedance-quality.md",
            "memory/2026-07-20-transition-motion-v2.md",
            "memory/2026-07-20-seedance-quality.md",
            "memory/2026-07-20-session-index.md",
        ):
            p = ROOT / name
            self.assertTrue(p.is_file(), f"missing {p}")
            text = p.read_text(encoding="utf-8")
            self.assertTrue(len(text) > 80, name)

    def test_skill_points_to_docs(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        post_card = (ROOT / "references" / "stages" / "post.md").read_text(encoding="utf-8")
        routing = (ROOT / "registry" / "context-routing.json").read_text(encoding="utf-8")
        index = (ROOT / "references" / "INDEX.md").read_text(encoding="utf-8")
        reachable = skill + post_card + index
        self.assertIn("cut-silk-bilingual.md", reachable)
        self.assertIn("hf-remotion-capability-matrix.md", reachable)
        self.assertIn("caption_mode", reachable)
        self.assertIn("transition_fluency", reachable)
        self.assertIn('"post"', routing)
        self.assertIn("context_refs", skill)

    def test_sediment_opt8_opt9(self) -> None:
        text = (ROOT / "references" / "lessons-2026-07-20-sediment-cn-codex.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Opt8", text)
        self.assertIn("Opt9", text)
        self.assertIn("camera_axis", text)
        self.assertIn("403", text)
        self.assertIn("transition-motion-v2", text)

    def test_schema_and_example_camera_axis(self) -> None:
        schema = (ROOT / "schemas" / "film-spec.schema.json").read_text(encoding="utf-8")
        ex = (ROOT / "templates" / "film-spec.example.json").read_text(encoding="utf-8")
        self.assertIn("camera_axis", schema)
        self.assertIn("dolly_in", schema)
        self.assertIn("camera_axis", ex)
        self.assertIn("legacy-img2video", ex)


class TransitionFluencyTests(unittest.TestCase):
    def test_continue_always_hard(self) -> None:
        from edit_policy import suggest_join_intent

        self.assertEqual(
            suggest_join_intent("hook", "approach", next_chain_mode="continue", fluency="silk"),
            "hard",
        )
        self.assertEqual(
            suggest_join_intent("action", "action", next_chain_mode="continue", fluency="silk"),
            "hard",
        )

    def test_enforce_continue_hard_overrides_author_soft(self) -> None:
        from edit_policy import enforce_continue_hard_joins

        intents = ["soft", "soft", "hold"]
        chains = ["cut", "continue", "continue", "cut"]  # joins into 1,2,3
        fixed, notes = enforce_continue_hard_joins(intents, chains)
        self.assertEqual(fixed, ["hard", "hard", "hold"])
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0]["to"], "hard")

    def test_camera_axis_rotation_avoids_recent(self) -> None:
        from edit_policy import suggest_camera_axis

        a = suggest_camera_axis("hook", previous_axes=[], shot_index=0)
        b = suggest_camera_axis("approach", previous_axes=[a], shot_index=1)
        c = suggest_camera_axis("action", previous_axes=[a, b], shot_index=2)
        self.assertNotEqual(a, b)
        # third should not equal both previous if menu allows
        self.assertTrue(c)
        self.assertNotEqual(c, b)

    def test_inject_camera_axis_phrase(self) -> None:
        from edit_policy import infer_camera_axis, inject_camera_axis_phrase

        m = inject_camera_axis_phrase("hand raises tray, idle not speaking", "locked")
        self.assertIn("locked-off", m.lower())
        self.assertEqual(infer_camera_axis(m), "locked")

    def test_silk_softens_some_scene_cuts(self) -> None:
        from edit_policy import suggest_join_intent

        # hook→approach default hard when punchy; silk may soft
        self.assertEqual(
            suggest_join_intent("hook", "approach", fluency="silk"),
            "soft",
        )
        self.assertEqual(
            suggest_join_intent("hook", "approach", fluency="punchy"),
            "hard",
        )

    def test_suggest_intents_uses_chain_modes(self) -> None:
        from edit_policy import suggest_transition_intents

        beats = ["hook", "approach", "action"]
        chains = ["cut", "continue", "continue"]
        intents = suggest_transition_intents(beats, chain_modes=chains, fluency="silk")
        self.assertEqual(len(intents), 2)
        # join into shot1 (approach) continue → hard; into shot2 continue → hard
        self.assertEqual(intents[0], "hard")
        self.assertEqual(intents[1], "hard")


class CaptionFormatTests(unittest.TestCase):
    def test_format_dual(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from export_composition import format_caption_lines

        d = format_caption_lines("中文一行", "English line", mode="zh_en")
        self.assertEqual(d["html_kind"], "dual")
        self.assertIn("中文一行", d["text"])
        self.assertIn("English line", d["text"])
        self.assertEqual(d["zh"], "中文一行")
        self.assertEqual(d["en"], "English line")

    def test_format_zh_only(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from export_composition import format_caption_lines

        d = format_caption_lines("只有中文", "", mode="zh_en")
        self.assertEqual(d["html_kind"], "single")
        self.assertEqual(d["text"], "只有中文")

    def test_film_spec_defaults_caption_and_fluency(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from film_spec import validate_film_spec

        spec = {
            "title": "测试片名足够长了",
            "vo_mode": "storyteller",
            "dramatic_meaning_strict": False,
            "director_intent": {
                "logline": "一句话卖点要够八个字以上",
                "tone": "色气·俏皮",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "hook",
                            "nar": "短旁白一句。",
                            "dsl": {
                                "subject": "s",
                                "action": "pulls curtain",
                                "motion": "pulls curtain open, body steps in, soft breath, idle not speaking",
                                "chain_mode": "cut",
                            },
                        },
                        {
                            "id": "shot02",
                            "dramatic_function": "approach",
                            "nar": "第二句旁白。",
                            "nar_en": "Second line EN.",
                            "dsl": {
                                "subject": "s",
                                "action": "steps closer",
                                "motion": "steps closer continuous, slow push-in, soft blink, idle not speaking",
                                "chain_mode": "continue",
                            },
                        },
                    ]
                }
            ],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(spec.get("caption_mode"), "zh")
        self.assertEqual(spec.get("transition_fluency"), "silk")
        # grok_primary season: auto resolves to Grok image_to_video.
        self.assertEqual(spec.get("i2v_provider"), "grok")
        intents = spec.get("transition_intents") or []
        self.assertEqual(len(intents), 1)
        # join into continue shot → hard
        self.assertEqual(intents[0], "hard")


if __name__ == "__main__":
    unittest.main()
