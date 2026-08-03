"""Structural checks for retained FRW history and the current fallback contract."""

from __future__ import annotations

import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references" / "frw-degrade-dispatch.md"
LESSON_FRW = ROOT / "references" / "lessons-2026-07-20-frw-2v-first.md"
LESSON_SEED = ROOT / "references" / "lessons-2026-07-20-seedance-quality.md"
LESSON_LTX = ROOT / "references" / "lessons-2026-07-20-frw-ltx-probe.md"
SKILL = ROOT / "SKILL.md"
CONSISTENCY = ROOT / "references" / "consistency.md"
PRODUCTION = ROOT / "references" / "production-discipline.md"
SEDIMENT = ROOT / "references" / "lessons-2026-07-20-sediment-cn-codex.md"
MEDIA_QA = ROOT / "scripts" / "media_qa.py"
FILM_SPEC = ROOT / "scripts" / "film_spec.py"
FRW_LAUNCHER = ROOT / "scripts" / "frw_dispatch.py"
EXAMPLE = ROOT / "templates" / "film-spec.example.json"
SCHEMA = ROOT / "schemas" / "film-spec.schema.json"


@pytest.mark.slow
class FrwDegradeDocsTests(unittest.TestCase):
    @pytest.mark.slow
    def test_frw_degrade_reference_seedance_first(self) -> None:
        self.assertTrue(REF.is_file(), f"missing {REF}")
        text = REF.read_text(encoding="utf-8")
        for needle in (
            "seedance-2-fast-i2v",
            "newvideo",
            "frw_seedance_i2v",
            "reencode-clips",
            "protocol_version",
            "frw_dispatch",
            "legacy-img2video",
            "720p",
            "i2v_provider",
            "frw_video_model",
            "禁止",
            "Grok",
        ):
            self.assertIn(needle, text, f"missing {needle!r} in frw-degrade-dispatch.md")
        self.assertIn("Seedance", text)
        # Must still acknowledge legacy exists but not as default
        self.assertIn("img2video", text)
        low = text.lower()
        self.assertIn("image_to_video", low)

    @pytest.mark.slow
    def test_skill_yaml_and_body_seedance(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        visual_card = (ROOT / "references" / "stages" / "visual.md").read_text(encoding="utf-8")
        reachable = skill + visual_card
        # Current season: Grok action primary; dialogue still FRW LTX 2.3.
        self.assertIn("grok_primary", reachable)
        self.assertIn("LTX 2.3", skill)
        self.assertIn("FRW API I2V", skill)
        self.assertIn("frw-degrade-dispatch.md", reachable)
        degrade = REF.read_text(encoding="utf-8")
        seedance_lesson = LESSON_SEED.read_text(encoding="utf-8")
        self.assertIn("lessons-2026-07-20-seedance-quality.md", degrade)
        self.assertIn("不是默认 bulk", seedance_lesson)
        self.assertIn("AIFILM_I2V_PROFILE", degrade)
        desc_line = next(
            (ln for ln in skill.splitlines() if ln.startswith("description:")),
            "",
        )
        self.assertIn("Grok Imagine", desc_line)
        self.assertNotIn("默认 FRW 2V 优先", desc_line)

    @pytest.mark.slow
    def test_consistency_and_production_seedance(self) -> None:
        cons = CONSISTENCY.read_text(encoding="utf-8")
        prod = PRODUCTION.read_text(encoding="utf-8")
        for text, label in ((cons, "consistency"), (prod, "production-discipline")):
            self.assertIn("FRW LTX", text, label)
            self.assertIn("Grok", text, label)
            self.assertIn("FRW API I2V", text, label)
            self.assertIn("Video 1.5", text, label)
        self.assertIn("ltx23_primary", cons)
        self.assertNotIn("推荐 576×1024", cons)

    @pytest.mark.slow
    def test_sediment_opt5_seedance(self) -> None:
        if not SEDIMENT.is_file():
            self.skipTest("sediment crosswalk missing")
        text = SEDIMENT.read_text(encoding="utf-8")
        self.assertIn("Opt4", text)
        self.assertIn("Opt5", text)
        self.assertIn("seedance-2-fast-i2v", text)
        self.assertIn("frw_seedance_i2v", text)
        self.assertIn("FRW Seedance", text)
        # Opt9: 403 fallback must not push agents back to legacy default
        self.assertIn("Opt9", text)
        self.assertIn("403", text)
        self.assertIn("Grok", text)

    @pytest.mark.slow
    def test_lessons_exist(self) -> None:
        self.assertTrue(LESSON_FRW.is_file(), f"missing {LESSON_FRW}")
        self.assertTrue(LESSON_SEED.is_file(), f"missing {LESSON_SEED}")
        self.assertTrue(LESSON_LTX.is_file(), f"missing {LESSON_LTX}")
        frw = LESSON_FRW.read_text(encoding="utf-8")
        seed = LESSON_SEED.read_text(encoding="utf-8")
        ltx = LESSON_LTX.read_text(encoding="utf-8")
        self.assertIn("P1", frw)
        self.assertIn("seedance-2-fast-i2v", frw)
        self.assertIn("seedance-2-fast-i2v", seed)
        self.assertIn("348771", seed)
        self.assertIn("frw_seedance_i2v", seed)
        self.assertIn("P0", seed)
        # LTX probe contract
        self.assertIn("ltx-t2v", ltx)
        self.assertIn("ltx-i2v", ltx)
        self.assertIn("string", ltx.lower())
        self.assertIn("720", ltx)
        self.assertIn("1280", ltx)
        self.assertIn("502", ltx)
        self.assertIn("image_url", ltx)

    @pytest.mark.slow
    def test_ltx_in_dispatch_and_film_spec_models(self) -> None:
        ref = REF.read_text(encoding="utf-8")
        self.assertIn("ltx-i2v", ref)
        self.assertIn("ltx-t2v", ref)
        self.assertIn("720", ref)
        self.assertIn("string", ref.lower())
        fs = FILM_SPEC.read_text(encoding="utf-8")
        self.assertIn("ltx-i2v", fs)
        self.assertIn("ltx-t2v", fs)
        self.assertIn("DEFAULT_LTX_WIDTH", fs)
        self.assertIn("FRW_I2V_FALLBACK_CHAIN", fs)
        qa = MEDIA_QA.read_text(encoding="utf-8")
        self.assertIn("frw_ltx_i2v", qa)

    @pytest.mark.slow
    def test_media_qa_and_film_spec_code(self) -> None:
        self.assertTrue(FRW_LAUNCHER.is_file(), f"missing {FRW_LAUNCHER}")
        qa = MEDIA_QA.read_text(encoding="utf-8")
        for ep in (
            "frw_seedance_i2v",
            "frw_seedance_flf",
            "frw_newvideo",
            "frw_img2video",
            "frw_first_last_frame",
            "frw_video_continue",
            "image_to_video",
            "external",
        ):
            self.assertIn(ep, qa)
        fs = FILM_SPEC.read_text(encoding="utf-8")
        self.assertIn('FRW_I2V_FRW_ONLY_LIFEBOAT = "legacy-img2video"', fs)
        self.assertIn("DEFAULT_FRW_VIDEO_MODEL = FRW_I2V_FRW_ONLY_LIFEBOAT", fs)
        self.assertIn('DEFAULT_FRW_RESOLUTION = "720p"', fs)
        self.assertIn("legacy-img2video", fs)
        launcher = FRW_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("img2video-audio", launcher)
        self.assertIn("newvideo", launcher)

    @pytest.mark.slow
    def test_example_and_schema_fields(self) -> None:
        ex = EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("legacy-img2video", ex)
        self.assertIn("frw_video_model", ex)
        self.assertIn("720p", ex)
        schema = SCHEMA.read_text(encoding="utf-8")
        self.assertIn("frw_video_model", schema)
        self.assertIn("seedance-2-fast-i2v", schema)
        self.assertIn("i2v_provider", schema)

    @pytest.mark.slow
    def test_film_spec_defaults_runtime(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from film_spec import (  # type: ignore
            DEFAULT_FRW_ENV_MODEL,
            DEFAULT_FRW_VIDEO_MODEL,
            DEFAULT_I2V_PROVIDER,
            default_i2v_provider,
            validate_film_spec,
        )

        # Constants: provider is profile-resolved ("auto"); FRW model ids stay documented
        self.assertEqual(DEFAULT_I2V_PROVIDER, "auto")
        self.assertEqual(DEFAULT_FRW_VIDEO_MODEL, "legacy-img2video")
        self.assertEqual(DEFAULT_FRW_ENV_MODEL, "ltx-t2v")
        self.assertEqual(default_i2v_provider(), "grok")
        spec = {
            "title": "grok-primary-default-probe",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "测试 ltx23_primary 默认写入 film-spec 的行为。",
                "tone": "neutral",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "hook",
                            "nar": "话说门关上了。",
                            "dsl": {
                                "subject": "adult woman",
                                "action": "closes the door latch",
                                "motion": "hand turns latch shut, soft blink",
                                "cast": ["heroine"],
                            },
                        },
                        {
                            "id": "shot02",
                            "shot_role": "env",
                            "dramatic_function": "bridge",
                            "nar": "灯牌在雨里闪。",
                            "dsl": {
                                "subject": "neon sign rain no people",
                                "action": "neon flickers",
                                "motion": "neon flicker, rain on glass, camera static locked-off, idle not speaking",
                            },
                        },
                    ]
                }
            ],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(spec.get("i2v_provider"), "grok")
        self.assertEqual(spec.get("frw_video_model"), "legacy-img2video")
        self.assertEqual(spec.get("frw_env_model"), "ltx-t2v")
        self.assertEqual(spec.get("frw_resolution"), "720p")
        self.assertEqual(spec.get("frw_aspect_ratio"), "9:16")
        self.assertEqual(spec["scenes"][0]["shots"][0].get("shot_role"), "hero")
        self.assertEqual(spec["scenes"][0]["shots"][1].get("shot_role"), "env")
        self.assertIn("hero_motion_primary", (spec.get("_layer_routing") or {}))
        self.assertEqual(
            (spec.get("_layer_routing") or {}).get("env_synth_primary"),
            "frw_ltx_t2v",
        )


if __name__ == "__main__":
    unittest.main()
