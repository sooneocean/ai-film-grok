"""final blocks on preflight hard gates unless --skip-preflight."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402


def _seed_ecchi_dark(root: Path) -> None:
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    (root / "out").mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}}),
        encoding="utf-8",
    )
    (root / "style-bible.json").write_text(
        json.dumps({"locked": True, "identity_lock": "halo"}),
        encoding="utf-8",
    )
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "色气片",
                "vo_mode": "storyteller",
                "tts_backend": "edge",
                "director_intent": {
                    "logline": "雨夜后座升温的完整承诺句。",
                    "tone": "色气·诱惑",
                    "emotional_arc": ["a", "b", "c"],
                },
                "sound_plan": {"mood": "dark"},
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "shot01",
                                "dramatic_function": "hook",
                                "nar": "话说夜里。",
                                "duration_sec": 6,
                                "dsl": {
                                    "subject": "a",
                                    "action": "b",
                                    "motion": "slow push-in, soft blink, idle not speaking",
                                },
                            }
                        ]
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class FinalPreflightGateTests(unittest.TestCase):
    def test_final_blocked_by_ecchi_dark_bgm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_ecchi_dark(root)
            args = argparse.Namespace(
                root=str(root),
                post_engine="ffmpeg",
                allow_loop_risk=False,
                skip_preflight=False,
                preflight_strict=False,
                out_name=None,
                voice=None,
                tts_backend=None,
                vo_rate=None,
                vo_pitch=None,
                vo_gain=None,
                title=None,
                end_title=None,
                music=None,
                music_license=None,
                music_volume=None,
                transition_sec=None,
                native_audio_volume=None,
                music_mood="rnb",
                lipsync="off",
                sub_lead=None,
                sub_max_unit=None,
                sub_max_chars=None,
                title_dur=None,
                subs=None,
                compose_quality="standard",
                skip_compose_check=False,
                keep_compose_raw=False,
            )
            with self.assertRaises(aifilm_grok.FilmError) as ctx:
                aifilm_grok.cmd_final(args)
            msg = str(ctx.exception)
            self.assertIn("preflight hard", msg)
            self.assertIn("ecchi_dark_bgm", msg)

    def test_skip_preflight_reaches_loop_gate_or_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_ecchi_dark(root)
            args = argparse.Namespace(
                root=str(root),
                post_engine="ffmpeg",
                allow_loop_risk=True,
                skip_preflight=True,
                preflight_strict=False,
                out_name=None,
                voice=None,
                tts_backend="edge",
                vo_rate=None,
                vo_pitch=None,
                vo_gain=None,
                title=None,
                end_title=None,
                music=None,
                music_license=None,
                music_volume=None,
                transition_sec=None,
                native_audio_volume=None,
                music_mood="rnb",
                lipsync="off",
                sub_lead=None,
                sub_max_unit=None,
                sub_max_chars=None,
                title_dur=None,
                subs=None,
                compose_quality="standard",
                skip_compose_check=False,
                keep_compose_raw=False,
            )
            # Skip preflight lesson gates; inventory still fails closed when
            # film-spec shots ≠ approved clips (sediment gate — not skippable).
            with self.assertRaises(aifilm_grok.FilmError) as ctx:
                aifilm_grok.cmd_final(args)
            msg = str(ctx.exception).lower()
            self.assertIn("inventory", msg)
            self.assertNotIn("preflight hard", msg)


if __name__ == "__main__":
    unittest.main()
