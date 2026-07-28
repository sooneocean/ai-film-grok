"""Tests for stretch, transition, and motion policies (shipped code)."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import edit_policy  # noqa: E402
import media_qa  # noqa: E402
import render_final  # noqa: E402
import tts_backend  # noqa: E402


def _make_moving_clip(path: Path, *, duration: float = 2.0, fps: int = 30) -> None:
    """Synthetic clip with real motion (testsrc2 + scroll) for motion_ok probes."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x568:rate={fps}:duration={duration}",
            "-vf",
            "format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "30",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.slow
class EditPolicyUnitTests(unittest.TestCase):
    @pytest.mark.slow
    def test_plan_stretch_long_target_is_loop_not_freeze(self) -> None:
        # Use a long (non-shortform) plate so loop is permitted: shortform
        # (src <= 7.5s) forbids loop to prevent "跑两遍" double-play.
        plan = edit_policy.plan_stretch(10.0, 24.0)
        self.assertEqual(plan["mode"], "loop")
        self.assertEqual(plan["freeze_sec"], 0.0)
        self.assertGreaterEqual(plan["loops"], 1)

    @pytest.mark.slow
    def test_plan_stretch_upgrades_heavy_pad_to_loop(self) -> None:
        # Mild ratio but would freeze most of extension if pad unlimited
        plan = edit_policy.plan_stretch(2.0, 2.0 * 1.20)
        # may be setpts or loop depending on pad; freeze never exceeds max
        self.assertLessEqual(plan["freeze_sec"], edit_policy.MAX_FREEZE_PAD_SEC + 1e-6)
        if plan["mode"] == "loop":
            self.assertEqual(plan["freeze_sec"], 0.0)

    @pytest.mark.slow
    def test_plan_stretch_hook_forbids_loop(self) -> None:
        # hook/action must not stream_loop even when target >> src
        plan = edit_policy.plan_stretch(6.0, 7.0, dramatic_function="hook")
        self.assertEqual(plan["loops"], 0)
        self.assertNotEqual(plan["mode"], "loop")
        self.assertTrue(plan.get("forbid_loop"))

    @pytest.mark.slow
    def test_plan_stretch_action_forbids_loop_fails_if_too_long(self) -> None:
        # 6s plate cannot cover 14s VO without loop → PolicyError
        with self.assertRaises(edit_policy.PolicyError):
            edit_policy.plan_stretch(6.0, 14.0, dramatic_function="action")

    @pytest.mark.slow
    def test_xfade_filter_graph_enabled_for_multi_clip(self) -> None:
        graph = edit_policy.build_xfade_filter_graph([2.0, 2.0, 2.0], transition_sec=0.25)
        self.assertTrue(graph["enabled"])
        self.assertIn("xfade=", graph["filter_complex"])
        self.assertEqual(graph["n_inputs"], 3)
        expected = edit_policy.xfade_output_duration([2.0, 2.0, 2.0], 0.25)
        self.assertAlmostEqual(graph["output_duration"], expected, places=2)
        self.assertLess(graph["output_duration"], 6.0)

    @pytest.mark.slow
    def test_xfade_disabled_when_zero(self) -> None:
        graph = edit_policy.build_xfade_filter_graph([2.0, 2.0], transition_sec=0.0)
        self.assertFalse(graph["enabled"])
        self.assertEqual(graph["filter_complex"], "")

    @pytest.mark.slow
    def test_acrossfade_graph(self) -> None:
        g = edit_policy.build_acrossfade_filter_graph(3, transition_sec=0.22)
        self.assertTrue(g["enabled"])
        self.assertIn("acrossfade=", g["filter_complex"])

    @pytest.mark.slow
    def test_validate_motion_requires_cues_and_rejects_mouth_primary(self) -> None:
        ok = edit_policy.validate_motion("slow push-in, soft blink, breath, idle not speaking")
        self.assertIn("push", ok.lower())
        with self.assertRaises(edit_policy.PolicyError):
            edit_policy.validate_motion("")
        with self.assertRaises(edit_policy.PolicyError):
            edit_policy.validate_motion("mouth speaking")
        with self.assertRaises(edit_policy.PolicyError):
            edit_policy.validate_motion("just vibes")  # no positive motion hints


class TimelineSyncTests(unittest.TestCase):
    """Subtitle/native starts must track xfade offsets, not hard-cut cumulative targets."""

    @pytest.mark.slow
    def test_segment_timeline_matches_xfade_offsets(self) -> None:
        durs = [1.0, 6.0, 6.0, 6.0, 6.0, 1.0]  # title + 4 shots + end
        t = 0.22
        tl = edit_policy.segment_timeline(durs, t)
        graph = edit_policy.build_xfade_filter_graph(durs, transition_sec=t)
        self.assertTrue(tl["enabled"])
        self.assertEqual(tl["starts"][1:], graph["offsets"])
        self.assertAlmostEqual(tl["output_duration"], graph["output_duration"], places=4)
        # lag vs hard-cut: by shot 5 (index 4 story = segment 5), hard is ahead by ~4*0.22
        hard = 0.0
        for i, _d in enumerate(durs):
            if i == 0:
                continue
            hard += durs[i - 1]
            if i >= 2:  # after first join into story
                self.assertLess(tl["starts"][i], hard - 0.05)

    @pytest.mark.slow
    def test_subtitle_cues_align_to_xfade_shot_starts(self) -> None:
        title_dur = 1.0
        end_dur = 1.0
        transition = 0.22
        shots = [
            {"id": "s1", "target": 6.0, "vo_dur": 5.0, "units": ["第一镜旁白。"]},
            {"id": "s2", "target": 6.0, "vo_dur": 5.0, "units": ["第二镜旁白。"]},
            {"id": "s3", "target": 6.0, "vo_dur": 5.0, "units": ["第三镜旁白。"]},
            {"id": "s4", "target": 6.0, "vo_dur": 5.0, "units": ["第四镜旁白。"]},
            {"id": "s5", "target": 6.0, "vo_dur": 5.0, "units": ["第五镜旁白。"]},
        ]
        cues, film_tl = render_final.build_subtitle_cues_for_shots(
            shots,
            title_duration=title_dur,
            end_duration=end_dur,
            transition_sec=transition,
            sub_lead=0.0,
        )
        # Same plan as video concat uses
        durs = [title_dur] + [s["target"] for s in shots] + [end_dur]
        xfade = edit_policy.build_xfade_filter_graph(durs, transition_sec=transition)
        visual_shot_starts = xfade["starts"][1 : 1 + len(shots)]
        for i, start in enumerate(visual_shot_starts):
            self.assertAlmostEqual(film_tl["shot_starts"][i], start, places=4)
        # First cue of each shot must open near visual start (not hard-cut lag)
        hard_t0 = title_dur
        for i, shot in enumerate(shots):
            shot_cues = [c for c in cues if c.get("shot_index") == i]
            self.assertTrue(shot_cues, f"missing cues for shot {i}")
            first = shot_cues[0]["start"]
            self.assertAlmostEqual(first, visual_shot_starts[i], delta=0.05)
            # Prove hard-cut would have drifted: by shot 4 (i=4) lag ≈ 4*0.22
            if i >= 2:
                self.assertLess(first, hard_t0 - 0.1)
            hard_t0 += shot["target"]

    @pytest.mark.slow
    def test_native_track_shortens_with_acrossfade_like_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            audio = root / "audio"
            work.mkdir()
            audio.mkdir()
            stem = root / "native.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(stem),
                ],
                check=True,
                capture_output=True,
            )
            title_dur = 0.5
            end_dur = 0.5
            targets = [2.0, 2.0, 2.0]
            transition = 0.25
            track = render_final.build_native_track(
                [{"id": f"s{i}", "target": t, "native_audio": stem} for i, t in enumerate(targets)],
                title_duration=title_dur,
                end_duration=end_dur,
                work=work,
                audio_dir=audio,
                transition_sec=transition,
            )
            hard_sum = title_dur + sum(targets) + end_dur
            expected = edit_policy.segment_timeline([title_dur] + targets + [end_dur], transition)[
                "output_duration"
            ]
            dout = render_final.pdur(track)
            self.assertLess(dout, hard_sum - 0.2)
            self.assertAlmostEqual(dout, expected, delta=0.25)


@pytest.mark.slow
class StretchAndTransitionIntegrationTests(unittest.TestCase):
    @pytest.mark.slow
    def test_stretch_clip_long_target_preserves_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            dest = root / "out.mp4"
            # Use a non-shortform plate (>= 8s) so loop is permitted for the
            # long-target stretch; shortform (<= 7.5s) forbids loop.
            _make_moving_clip(src, duration=8.0)
            plan = render_final.stretch_clip(src, dest, target=20.0, width=320, height=568, fps=30)
            self.assertEqual(plan["mode"], "loop")
            self.assertEqual(plan["freeze_sec"], 0.0)
            self.assertTrue(dest.is_file())
            qa = media_qa.analyze_media(dest, require_audio=False, require_motion=True)
            self.assertTrue(qa.get("ok"), qa)
            self.assertTrue(qa.get("motion_ok"), qa)
            self.assertGreaterEqual(qa.get("duration_sec", 0), 18.0)

    @pytest.mark.slow
    def test_concat_videos_inserts_xfade_shortening_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.mp4"
            b = root / "b.mp4"
            out = root / "joined.mp4"
            _make_moving_clip(a, duration=2.0)
            _make_moving_clip(b, duration=2.0)
            plan = render_final.concat_videos([a, b], out, transition_sec=0.25, fps=30)
            self.assertTrue(plan.get("enabled"))
            self.assertEqual(plan.get("method"), "xfade")
            self.assertIn("xfade=", plan.get("filter_complex", ""))
            self.assertTrue(out.is_file())
            da = render_final.pdur(a)
            db = render_final.pdur(b)
            dout = render_final.pdur(out)
            # xfade shortens vs hard sum
            self.assertLess(dout, da + db - 0.05)
            self.assertGreater(dout, da + db - 0.25 * 2)  # not over-shortened

    @pytest.mark.slow
    def test_concat_videos_hard_cut_when_transition_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.mp4"
            b = root / "b.mp4"
            out = root / "joined.mp4"
            _make_moving_clip(a, duration=1.0)
            _make_moving_clip(b, duration=1.0)
            plan = render_final.concat_videos([a, b], out, transition_sec=0.0, fps=30)
            self.assertFalse(plan.get("enabled"))
            self.assertEqual(plan.get("method"), "hard_concat")
            dout = render_final.pdur(out)
            self.assertAlmostEqual(dout, 2.0, delta=0.15)


@pytest.mark.slow
class TTSVoiceLockTests(unittest.TestCase):
    @pytest.mark.slow
    def test_mimo_uses_openai_compatible_request_and_writes_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mimo.mp3"
            audio = b"ID3" + b"mimo-test-audio" * 40
            response = mock.MagicMock()
            response.read.return_value = json.dumps(
                {
                    "choices": [
                        {"message": {"audio": {"data": base64.b64encode(audio).decode("ascii")}}}
                    ]
                }
            ).encode("utf-8")
            cm = mock.MagicMock()
            cm.__enter__.return_value = response
            with (
                mock.patch.object(tts_backend, "mimo_api_key", return_value="test-key"),
                mock.patch.object(
                    tts_backend, "mimo_api_base", return_value="https://mimo.test/v1"
                ),
                mock.patch.object(tts_backend, "mimo_tts_model", return_value="mimo-v2.5-tts"),
                mock.patch.object(tts_backend, "mimo_tts_voice", return_value="冰糖"),
                mock.patch.object(
                    tts_backend.urllib.request, "urlopen", return_value=cm
                ) as urlopen,
                mock.patch.object(
                    tts_backend.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, stdout="1.0\n"),
                ),
            ):
                result = tts_backend.tts_mimo("测试旁白", out)

            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), audio)
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, "https://mimo.test/v1/chat/completions")
            self.assertEqual(request.get_header("Api-key"), "test-key")
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], "mimo-v2.5-tts")
            self.assertEqual(payload["audio"], {"format": "mp3", "voice": "冰糖"})
            self.assertEqual(payload["messages"][1], {"role": "assistant", "content": "测试旁白"})

    @pytest.mark.slow
    def test_mimo_bad_audio_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mimo.mp3"
            response = mock.MagicMock()
            response.read.return_value = (
                b'{"choices":[{"message":{"audio":{"data":"not base64"}}}]}'
            )
            cm = mock.MagicMock()
            cm.__enter__.return_value = response
            with (
                mock.patch.object(tts_backend, "mimo_api_key", return_value="test-key"),
                mock.patch.object(tts_backend.urllib.request, "urlopen", return_value=cm),
                self.assertRaisesRegex(tts_backend.TTSError, "missing valid base64 audio"),
            ):
                tts_backend.tts_mimo("测试旁白", out)
            self.assertFalse(out.exists())

    @pytest.mark.slow
    def test_mimo_empty_text_fails_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mimo.mp3"
            with (
                mock.patch.object(tts_backend, "mimo_api_key", return_value="test-key"),
                mock.patch.object(tts_backend.urllib.request, "urlopen") as urlopen,
                self.assertRaisesRegex(tts_backend.TTSError, "non-empty text"),
            ):
                tts_backend.tts_mimo("  ", out)
            urlopen.assert_not_called()
            self.assertFalse(out.exists())

    @pytest.mark.slow
    def test_mimo_undecodable_audio_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mimo.mp3"
            audio = b"ID3" + b"mimo-test-audio" * 40
            response = mock.MagicMock()
            response.read.return_value = json.dumps(
                {
                    "choices": [
                        {"message": {"audio": {"data": base64.b64encode(audio).decode("ascii")}}}
                    ]
                }
            ).encode("utf-8")
            cm = mock.MagicMock()
            cm.__enter__.return_value = response
            with (
                mock.patch.object(tts_backend, "mimo_api_key", return_value="test-key"),
                mock.patch.object(tts_backend.urllib.request, "urlopen", return_value=cm),
                mock.patch.object(
                    tts_backend.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 1, stdout=""),
                ),
                self.assertRaisesRegex(tts_backend.TTSError, "not decodable audio"),
            ):
                tts_backend.tts_mimo("测试旁白", out)
            self.assertFalse(out.exists())

    @pytest.mark.slow
    def test_fish_without_voice_id_fails_closed_unless_fallback_is_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out1 = Path(tmp) / "a.mp3"
            import os

            with (
                mock.patch.object(tts_backend, "_load_config_env"),
                mock.patch.dict(
                    os.environ,
                    {"AIFILM_TTS_STRICT_VOICE": "1", "FISH_API_KEY": "test-key"},
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(tts_backend.TTSError, "fixed FISH_VOICE_ID"):
                    tts_backend.synthesize(
                        "话说闭馆后的泳池。",
                        out1,
                        backend="fish",
                        voice="zh-CN-XiaoxiaoNeural",
                    )
                with self.assertRaisesRegex(tts_backend.TTSError, "explicit backends never"):
                    tts_backend.synthesize(
                        "即使允许 auto 降级，显式 Fish 也不换服务商。",
                        out1,
                        backend="fish",
                        voice="zh-CN-XiaoxiaoNeural",
                        allow_network_fallback=True,
                    )
            self.assertFalse(out1.exists())

    @pytest.mark.slow
    def test_explicit_configured_fish_without_voice_is_reported_unready(self) -> None:
        import os

        with (
            mock.patch.object(tts_backend, "_load_config_env"),
            mock.patch.dict(
                os.environ,
                {
                    "AIFILM_TTS_BACKEND": "fish",
                    "AIFILM_TTS_STRICT_VOICE": "1",
                    "FISH_API_KEY": "test-key",
                },
                clear=True,
            ),
        ):
            info = tts_backend.probe()
            self.assertFalse(info["ok"])
            self.assertEqual(info["active"], "fish")
            self.assertFalse(info["ready"]["fish"])

    @pytest.mark.slow
    def test_edge_locked_speaker_same_identity_twice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out1 = Path(tmp) / "a.mp3"
            out2 = Path(tmp) / "b.mp3"

            def fake_edge(_: str, out: Path, __: str, **___: object) -> Path:
                out.write_bytes(b"ID3" + b"offline-test-audio" * 40)
                return out

            with mock.patch.object(tts_backend, "tts_edge", side_effect=fake_edge):
                m1 = tts_backend.synthesize(
                    "话说闭馆后的泳池。",
                    out1,
                    backend="edge",
                    voice="zh-CN-XiaoxiaoNeural",
                )
                m2 = tts_backend.synthesize(
                    "她把你拽到栏杆边。",
                    out2,
                    backend="edge",
                    voice="zh-CN-XiaoxiaoNeural",
                )
            self.assertEqual(m1["backend"], "edge")
            self.assertEqual(m2["backend"], "edge")
            self.assertEqual(m1["voice"], m2["voice"])
            self.assertEqual(m1["voice"], "zh-CN-XiaoxiaoNeural")
            self.assertTrue(out1.is_file() and out1.stat().st_size > 500)
            self.assertTrue(out2.is_file() and out2.stat().st_size > 500)

    @pytest.mark.slow
    def test_probe_reports_strict_voice_lock_policy(self) -> None:
        info = tts_backend.probe()
        self.assertIn("strict_voice_lock", info)
        self.assertIn("locked_speaker_policy", info)
        self.assertIn("backends", info)


class FilmSpecMotionTests(unittest.TestCase):
    def _base_spec(self) -> dict:
        return {
            "title": "t",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "夜里靠近的完整 logline。",
                "tone": "quiet heat",
                "emotional_arc": ["enter", "near", "hold"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "hook",
                            "nar": "夜里。",
                            "dsl": {"subject": "woman", "action": "stands"},
                        }
                    ]
                }
            ],
        }

    @pytest.mark.slow
    def test_missing_motion_filled_from_beat_defaults(self) -> None:
        from film_spec import validate_film_spec

        base = self._base_spec()
        # no motion → coverage defaults from dramatic_function=hook
        shots = validate_film_spec(base, assign_missing_ids=False)
        self.assertEqual(len(shots), 1)
        self.assertTrue(shots[0]["dsl"]["motion"])
        self.assertIn("push", shots[0]["dsl"]["motion"].lower())
        self.assertEqual(shots[0]["dsl"]["camera"]["shot_size"], "medium full")
        self.assertIn("dsl.motion", shots[0].get("coverage_defaults_applied", {}).get("filled", []))

    @pytest.mark.slow
    def test_explicit_mouth_speaking_rejected(self) -> None:
        from film_spec import FilmSpecError, validate_film_spec

        bad = self._base_spec()
        bad["scenes"][0]["shots"][0]["dsl"]["motion"] = "mouth speaking"
        with self.assertRaises(FilmSpecError):
            validate_film_spec(bad, assign_missing_ids=False)

    @pytest.mark.slow
    def test_author_motion_wins_over_defaults(self) -> None:
        from film_spec import validate_film_spec

        good = self._base_spec()
        custom = "slow orbit, soft blink, breath, idle not speaking"
        good["scenes"][0]["shots"][0]["dsl"]["motion"] = custom
        # Author-owned size that still passes framing iron (no head-crop language)
        good["scenes"][0]["shots"][0]["dsl"]["camera"] = {"shot_size": "medium close"}
        good["scenes"][0]["shots"][0]["dsl"]["framing"] = (
            "full head and both shoulders inside frame, ample headroom, safe framing"
        )
        shots = validate_film_spec(good, assign_missing_ids=False)
        self.assertEqual(shots[0]["dsl"]["motion"], custom)
        self.assertEqual(shots[0]["dsl"]["camera"]["shot_size"], "medium close")
        # motion + shot_size author-owned; angle/framing may still be filled
        filled = shots[0].get("coverage_defaults_applied", {}).get("filled", [])
        self.assertNotIn("dsl.motion", filled)
        self.assertNotIn("dsl.camera.shot_size", filled)


if __name__ == "__main__":
    unittest.main()


@pytest.mark.slow
class EditorialCraftTests(unittest.TestCase):
    @pytest.mark.slow
    def test_continue_is_match_or_action_cut(self) -> None:
        c = edit_policy.suggest_edit_craft(
            "hook", "approach", next_chain_mode="continue", next_cut_on="mid_motion"
        )
        self.assertEqual(c, "cut_on_action")
        c2 = edit_policy.suggest_edit_craft("hook", "approach", next_chain_mode="continue")
        self.assertEqual(c2, "match_cut")
        self.assertEqual(edit_policy.craft_to_intent_style(c)[0], "hard")

    @pytest.mark.slow
    def test_smash_and_insert(self) -> None:
        self.assertEqual(edit_policy.suggest_edit_craft("action", "reaction"), "smash_cut")
        self.assertEqual(edit_policy.suggest_edit_craft("approach", "sensory"), "insert_cut")

    @pytest.mark.slow
    def test_soft_run_punctuated(self) -> None:
        crafts = ["soft_glue"] * 6
        out = edit_policy._punctuate_soft_run(crafts, fluency="silk")
        hardish = {
            "contrast_cut",
            "smash_cut",
            "montage_jump",
            "insert_cut",
            "match_cut",
            "cut_on_action",
        }
        self.assertTrue(any(c in hardish for c in out))

    @pytest.mark.slow
    def test_crafts_drive_intents_styles_length(self) -> None:
        beats = [
            "hook",
            "approach",
            "sensory",
            "reaction",
            "action",
            "afterglow",
        ]
        chains = ["", "continue", "continue", "cut", "continue", "cut"]
        crafts = edit_policy.suggest_edit_crafts(beats, chain_modes=chains, fluency="cinematic")
        self.assertEqual(len(crafts), 5)
        intents = edit_policy.edit_crafts_to_intents(crafts)
        styles = edit_policy.edit_crafts_to_styles(crafts)
        self.assertEqual(len(intents), 5)
        self.assertEqual(len(styles), 5)
        # continue joins hard
        self.assertEqual(intents[0], "hard")  # continue into approach
        self.assertEqual(intents[1], "hard")


@pytest.mark.slow
class CharacterStanceTests(unittest.TestCase):
    @pytest.mark.slow
    def test_viewpoint_and_focal_suggest(self) -> None:
        foc = edit_policy.suggest_focal_character("reaction", previous_focal="hero")
        self.assertTrue(foc)
        vp = edit_policy.suggest_viewpoint(
            "reaction", focal=foc, previous_focal="hero", previous_viewpoint="ots"
        )
        self.assertEqual(vp, "reaction_to")
        rev = edit_policy.suggest_viewpoint(
            "approach",
            focal="partner",
            previous_focal="hero",
            previous_viewpoint="ots",
            shot_index=2,
        )
        self.assertEqual(rev, "reverse")

    @pytest.mark.slow
    def test_look_axis_flips_on_reverse(self) -> None:
        self.assertEqual(edit_policy.suggest_look_axis("reverse", previous_look="left"), "right")
        self.assertEqual(edit_policy.suggest_look_axis("reverse", previous_look="right"), "left")

    @pytest.mark.slow
    def test_focal_change_drives_craft(self) -> None:
        c = edit_policy.suggest_edit_craft(
            "action",
            "reaction",
            focal_changed=True,
            next_viewpoint="reverse",
        )
        self.assertIn(c, {"contrast_cut", "smash_cut"})

    @pytest.mark.slow
    def test_coverage_injects_stance(self) -> None:
        shot = {
            "dramatic_function": "reaction",
            "dsl": {"motion": "eyes widen, soft breath, idle not speaking"},
        }
        rep = edit_policy.apply_coverage_defaults_to_shot(
            shot,
            dramatic_function="reaction",
            shot_index=3,
            previous_focal="hero",
            previous_viewpoint="ots",
            previous_look="left",
            cast_ids=["hero", "partner"],
        )
        dsl = shot["dsl"]
        self.assertIn(dsl.get("viewpoint"), edit_policy.VIEWPOINTS)
        self.assertTrue(dsl.get("focal_character"))
        self.assertIn(dsl.get("look_axis"), edit_policy.LOOK_AXES)
        self.assertIn(rep.get("viewpoint_source"), {"suggest", "author", "suggest_fallback"})

    @pytest.mark.slow
    def test_lint_viewpoint_flat(self) -> None:
        shots = [
            {
                "dramatic_function": "hook",
                "dsl": {"viewpoint": "objective", "focal_character": "hero"},
            }
            for _ in range(5)
        ]
        lint = edit_policy.lint_character_stance(shots)
        self.assertIn("VIEWPOINT_FLAT", lint.get("codes") or [])
