"""Failure-mode tests for cast_voices / cast_tts_backends normalization leaves.

Peeled from render_final() body (W4 internal-leaf extraction). These functions
are pure: deterministic, no I/O, no global state. Each test pins a failure
mode that used to live inline in the orchestrator.
"""

from __future__ import annotations

import unittest

from final.errors import RenderError
from final.voice import (
    HEROINE_ZH_VOICE,
    PARTNER_ZH_VOICE,
    STORYTELLER_VOICE,
    normalize_cast_tts_backends,
    normalize_cast_voices,
)


class NormalizeCastVoicesTests(unittest.TestCase):
    def test_non_dict_input_yields_chinese_defaults_not_raise(self) -> None:
        for bad in (None, [], "edge", 42):
            with self.subTest(bad=bad):
                out = normalize_cast_voices(bad)
                self.assertEqual(
                    out,
                    {
                        "heroine": HEROINE_ZH_VOICE,
                        "partner": PARTNER_ZH_VOICE,
                        "male_hero": PARTNER_ZH_VOICE,
                        "storyteller": STORYTELLER_VOICE,
                    },
                )

    def test_valid_entries_stripped_and_kept(self) -> None:
        out = normalize_cast_voices(
            {" heroine ": " zh-CN-XiaoxiaoNeural ", "partner": " zh-CN-YunxiNeural "}
        )
        self.assertEqual(out["heroine"], "zh-CN-XiaoxiaoNeural")
        self.assertEqual(out["partner"], "zh-CN-YunxiNeural")
        # defaults still filled for missing roles
        self.assertEqual(out["storyteller"], STORYTELLER_VOICE)
        self.assertEqual(out["male_hero"], PARTNER_ZH_VOICE)

    def test_non_string_and_empty_entries_dropped(self) -> None:
        out = normalize_cast_voices(
            {"heroine": "", "partner": 42, "storyteller": None, "  ": " x "}
        )
        # empty/non-str entries never reach the dict; defaults fill the roles
        self.assertEqual(out["heroine"], HEROINE_ZH_VOICE)
        self.assertEqual(out["partner"], PARTNER_ZH_VOICE)
        self.assertEqual(out["storyteller"], STORYTELLER_VOICE)
        self.assertNotIn("  ", out)

    def test_legacy_ja_jp_role_remap_to_chinese_locks(self) -> None:
        out = normalize_cast_voices(
            {
                "heroine": "ja-JP-NanamiNeural",
                "partner": "ja-JP-KeitaNeural",
                "male_hero": "ja-JP-DaichiNeural",
                "storyteller": "ja-JP-ShotaNeural",
            }
        )
        self.assertEqual(out["heroine"], HEROINE_ZH_VOICE)
        self.assertEqual(out["partner"], PARTNER_ZH_VOICE)
        self.assertEqual(out["male_hero"], PARTNER_ZH_VOICE)
        self.assertEqual(out["storyteller"], STORYTELLER_VOICE)

    def test_legacy_ja_short_prefix_remap(self) -> None:
        out = normalize_cast_voices({"heroine": "ja-NanamiNeural"})
        self.assertEqual(out["heroine"], HEROINE_ZH_VOICE)

    def test_unknown_role_ja_lock_falls_back_to_storyteller(self) -> None:
        out = normalize_cast_voices({"bystander": "ja-JP-UnknownNeural"})
        self.assertEqual(out["bystander"], STORYTELLER_VOICE)
        self.assertEqual(out["heroine"], HEROINE_ZH_VOICE)

    def test_clean_non_ja_entries_untouched(self) -> None:
        custom = "zh-CN-CustomNeural"
        out = normalize_cast_voices({"heroine": custom, "partner": custom})
        self.assertEqual(out["heroine"], custom)
        self.assertEqual(out["partner"], custom)


class NormalizeCastTtsBackendsTests(unittest.TestCase):
    def test_non_dict_raises_render_error(self) -> None:
        for bad in ("edge", 42, None, ["edge"]):
            with self.subTest(bad=bad):
                with self.assertRaises(RenderError):
                    normalize_cast_tts_backends(bad)

    def test_providers_lowercased_and_stripped(self) -> None:
        out = normalize_cast_tts_backends({"HEROINE": " Edge ", "partner": "fish"})
        # role keys are stripped but not case-folded; provider values are lowercased
        self.assertEqual(out, {"HEROINE": "edge", "partner": "fish"})

    def test_empty_and_non_string_values_dropped(self) -> None:
        out = normalize_cast_tts_backends({"heroine": "", "partner": 42, "storyteller": " edge "})
        self.assertEqual(out, {"storyteller": "edge"})

    def test_empty_dict_ok(self) -> None:
        self.assertEqual(normalize_cast_tts_backends({}), {})


if __name__ == "__main__":
    unittest.main()
