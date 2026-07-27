"""export-compose: HyperFrames / Remotion designed-post bridge."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
from export_composition import (  # noqa: E402
    ComposeExportError,
    caption_clock_offset_for,
    export_composition,
    parse_srt,
    remotion_captions,
    resolve_compose_preset,
)


def _minimal_spec(n_shots: int = 2) -> dict:
    shots = []
    for i in range(1, n_shots + 1):
        shots.append(
            {
                "id": f"shot{i:02d}",
                "dramatic_function": "hook" if i == 1 else "reaction",
                "nar": f"话说第{i}镜。" if i == 1 else f"她轻轻眨眼，第{i}镜。",
                "duration_sec": 6,
                "lipsync": False,
                "dsl": {
                    "subject": "woman",
                    "action": "looks",
                    "motion": "slow push-in, soft blink, breathing, idle not speaking",
                },
            }
        )
    return {
        "title": "compose-export-test",
        "vo_mode": "storyteller",
        "transition_sec": 0.28,
        "director_intent": {
            "logline": "测试设计后期导出桥接的完整一句话。",
            "tone": "测试",
            "emotional_arc": ["hook", "react", "end"],
        },
        "scenes": [{"shots": shots}],
    }


def _seed_film_root(root: Path, *, n_shots: int = 2) -> None:
    for name in ("clips", "out", "receipts", "keyframes", "prompts", "audio", "canonical"):
        (root / name).mkdir(parents=True, exist_ok=True)
    spec = _minimal_spec(n_shots)
    (root / "film-spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    clips = {}
    for i in range(1, n_shots + 1):
        sid = f"shot{i:02d}"
        clip = root / "clips" / f"{sid}.mp4"
        # minimal non-empty placeholder file (export does not decode)
        clip.write_bytes(b"\x00\x00fake-mp4-placeholder")
        clips[sid] = {
            "shot_id": sid,
            "path": str(clip),
            "status": "approved",
            "duration_sec": 6.0,
            "source_endpoint": "image_to_video",
            "identity_approved": True,
            "motion_approved": True,
            "sha256": "abc",
        }
    manifest = {
        "schema_version": 1,
        "title": "compose-export-test",
        "width": 720,
        "height": 1280,
        "fps": 30,
        "clips": clips,
        "gates": {"clips_complete": True},
        "outputs": {},
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.slow
class ParseSrtTests(unittest.TestCase):
    @pytest.mark.slow
    def test_parse_basic_srt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "final.srt"
            path.write_text(
                "1\n00:00:01,000 --> 00:00:02,500\n你好世界\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\n第二行\n",
                encoding="utf-8",
            )
            cues = parse_srt(path)
            self.assertEqual(len(cues), 2)
            self.assertAlmostEqual(cues[0]["start"], 1.0)
            self.assertAlmostEqual(cues[0]["end"], 2.5)
            self.assertEqual(cues[0]["text"], "你好世界")

    @pytest.mark.slow
    def test_remotion_caption_shape(self) -> None:
        caps = remotion_captions([{"start": 1.0, "end": 2.0, "text": "hi"}])
        self.assertEqual(caps[0]["startMs"], 1000)
        self.assertEqual(caps[0]["endMs"], 2000)
        self.assertIn("text", caps[0])


@pytest.mark.slow
class ExportCompositionTests(unittest.TestCase):
    @pytest.mark.slow
    def test_export_both_engines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2)
            result = export_composition(root, engine="both", force=True)
            self.assertTrue(result["ok"])
            self.assertEqual(result["shot_count"], 2)
            self.assertGreaterEqual(result["caption_count"], 1)
            hf = root / "compose" / "hyperframes" / "index.html"
            self.assertTrue(hf.is_file())
            html = hf.read_text(encoding="utf-8")
            self.assertIn('data-composition-id="main"', html)
            self.assertIn("clip-shot01", html)
            self.assertIn("window.__timelines", html)
            # HyperFrames requires in-project media/ (not ../../clips escape)
            self.assertIn('src="media/', html)
            self.assertNotIn("../../clips/", html)
            self.assertTrue((root / "compose" / "hyperframes" / "media").is_dir())
            self.assertTrue(any((root / "compose" / "hyperframes" / "media").glob("shot*")))
            # system fonts only — no undeclared CJK font families
            self.assertNotIn("PingFang", html)
            self.assertIn("font-family: sans-serif", html)
            rem = root / "compose" / "remotion" / "src" / "Film.tsx"
            self.assertTrue(rem.is_file())
            root_tsx = root / "compose" / "remotion" / "src" / "Root.tsx"
            self.assertTrue(root_tsx.is_file())
            self.assertIn("Composition", root_tsx.read_text(encoding="utf-8"))
            index_ts = root / "compose" / "remotion" / "src" / "index.ts"
            self.assertTrue(index_ts.is_file())
            caps = root / "compose" / "remotion" / "public" / "captions.json"
            self.assertTrue(caps.is_file())
            plan = json.loads(
                (root / "compose" / "remotion" / "media-copy-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(plan["items"]), 2)
            rem_pkg = json.loads(
                (root / "compose" / "remotion" / "package.json").read_text(encoding="utf-8")
            )
            self.assertIn("remotion", rem_pkg.get("dependencies") or {})
            self.assertIn("@remotion/cli", rem_pkg.get("dependencies") or {})
            self.assertEqual(
                (rem_pkg.get("ai_film_grok") or {}).get("kind"), "remotion-designed-post"
            )
            film_tsx = rem.read_text(encoding="utf-8")
            self.assertIn("OffthreadVideo", film_tsx)
            self.assertIn("staticFile", film_tsx)
            # title/caption wiring from film-spec
            self.assertIn("compose-export-test", film_tsx)
            cap_data = json.loads(caps.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(cap_data), 1)
            self.assertIn("startMs", cap_data[0])
            comp_data = json.loads(
                (root / "compose" / "remotion" / "public" / "composition-data.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("remotion", comp_data)
            self.assertEqual(comp_data["remotion"]["compositionId"], "Film")
            self.assertEqual(len(comp_data["remotion"]["shots"]), 2)
            pkg = json.loads((root / "compose" / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(pkg["kind"], "ai-film-grok-compose-export")
            self.assertIn("skill_load", pkg.get("post_policy") or {})

    @pytest.mark.slow
    def test_requires_approved_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            man["clips"]["shot01"]["status"] = "draft"
            (root / "manifest.json").write_text(
                json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            with self.assertRaises(ComposeExportError):
                export_composition(root, engine="hyperframes", force=True)

    @pytest.mark.slow
    def test_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            export_composition(root, engine="hyperframes", force=True)
            with self.assertRaisesRegex(ComposeExportError, "force"):
                export_composition(root, engine="hyperframes", force=False)

    @pytest.mark.slow
    def test_cli_export_compose_rejects_incomplete_clips(self) -> None:
        import argparse

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            man["clips"] = {}
            (root / "manifest.json").write_text(
                json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            ns = argparse.Namespace(
                root=str(root),
                engine="hyperframes",
                title_dur=1.5,
                end_dur=1.5,
                force=True,
                layout="auto",
                compose_preset="auto",
            )
            with self.assertRaises(aifilm_grok.FilmError):
                aifilm_grok.cmd_export_compose(ns)


@pytest.mark.slow
class ComposePresetAndCaptionClockTests(unittest.TestCase):
    @pytest.mark.slow
    def test_resolve_preset_auto_from_rnb_mood(self) -> None:
        self.assertEqual(
            resolve_compose_preset({"sound_plan": {"mood": "rnb"}}, "auto"),
            "ecchi-rnb",
        )
        self.assertEqual(
            resolve_compose_preset({"director_intent": {"tone": "色气暧昧"}}, "auto"),
            "ecchi-rnb",
        )
        self.assertEqual(
            resolve_compose_preset({"sound_plan": {"mood": "warm"}}, "auto"),
            "minimal",
        )
        self.assertEqual(resolve_compose_preset({}, "minimal"), "minimal")
        self.assertEqual(resolve_compose_preset({}, "ecchi-rnb"), "ecchi-rnb")

    @pytest.mark.slow
    def test_caption_clock_underlay_zero_multiclip_title(self) -> None:
        self.assertEqual(
            caption_clock_offset_for(
                layout="underlay", title_dur=1.5, caption_source="out/final.srt"
            ),
            0.0,
        )
        self.assertEqual(
            caption_clock_offset_for(
                layout="multiclip", title_dur=1.5, caption_source="out/final.srt"
            ),
            1.5,
        )

    @pytest.mark.slow
    def test_remotion_multiclip_packs_from_zero_and_shifts_captions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=2)
            result = export_composition(root, engine="remotion", force=True, layout="multiclip")
            self.assertTrue(result["ok"])
            meta = json.loads(
                (root / "compose" / "remotion" / "public" / "composition-data.json").read_text(
                    encoding="utf-8"
                )
            )
            rem = meta["remotion"]
            self.assertEqual(rem["layout"], "multiclip")
            self.assertEqual(rem["captionClockOffset"], 1.5)
            self.assertEqual(rem["shots"][0]["fromFrame"], 0)
            # second shot starts after first duration (packed)
            self.assertGreater(rem["shots"][1]["fromFrame"], 0)
            caps = json.loads(
                (root / "compose" / "remotion" / "public" / "captions.json").read_text(
                    encoding="utf-8"
                )
            )
            # seed SRT usually starts after title pad; shifted should be earlier
            if caps:
                self.assertGreaterEqual(caps[0]["startMs"], 0)
            cfg = (root / "compose" / "remotion" / "remotion.config.ts").read_text(encoding="utf-8")
            self.assertIn("setEntryPoint", cfg)
            pkg = json.loads(
                (root / "compose" / "remotion" / "package.json").read_text(encoding="utf-8")
            )
            self.assertIn("src/index.ts", pkg["scripts"]["render"])

    @pytest.mark.slow
    def test_underlay_preserves_srt_absolute_start(self) -> None:
        """Underlay must not subtract title pad (early SRT cues stay near t=0)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            # fake final film + SRT on absolute film clock
            (root / "out" / "film_final.mp4").write_bytes(b"\x00fake-final")
            (root / "out" / "final.srt").write_text(
                "1\n00:00:00,200 --> 00:00:01,200\n开场旁白\n",
                encoding="utf-8",
            )
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            man["outputs"] = {
                "final_film": {
                    "path": "film_final.mp4",
                    "duration_sec": 8.0,
                    "sha256": "x",
                }
            }
            (root / "manifest.json").write_text(
                json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = export_composition(
                root,
                engine="hyperframes",
                force=True,
                layout="underlay",
                compose_preset="minimal",
            )
            self.assertEqual(result["layout"], "underlay")
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-caption-clock-offset="0.000"', html)
            self.assertIn('data-compose-preset="minimal"', html)
            # first caption should start near 0.2s, not pushed by title_dur
            self.assertIn('data-start="0.200"', html)
            self.assertIn("开场旁白", html)

    @pytest.mark.slow
    def test_underlay_rejects_a_plate_that_already_burned_subtitles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            (root / "out" / "film_final.mp4").write_bytes(b"\x00fake-final")
            (root / "out" / "final-delivery.json").write_text(
                json.dumps({"subtitles": {"burned_in": True}}), encoding="utf-8"
            )
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["outputs"] = {
                "final_film": {"path": "film_final.mp4", "duration_sec": 8.0, "sha256": "x"}
            }
            (root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ComposeExportError, "double-burn"):
                export_composition(root, engine="hyperframes", force=True, layout="underlay")

    @pytest.mark.slow
    def test_underlay_end_roll_is_clamped_to_actual_plate_clock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            (root / "out" / "film_final.mp4").write_bytes(b"\x00fake-final")
            (root / "post-package.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "short-drama-platform-package",
                        "package_id": "clock-safe",
                        "outro": {"mode": "hook", "next_episode": "第 2 集"},
                    }
                ),
                encoding="utf-8",
            )
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["outputs"] = {
                "final_film": {"path": "film_final.mp4", "duration_sec": 8.0, "sha256": "x"}
            }
            (root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            export_composition(root, engine="hyperframes", force=True, layout="underlay")
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="end-roll"', html)
            self.assertIn('data-start="3.000" data-duration="5.000"', html)
            self.assertIn('data-duration="8.000"', html)

    @pytest.mark.slow
    def test_underlay_platform_intro_is_clamped_to_actual_plate_clock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            (root / "out" / "film_final.mp4").write_bytes(b"\x00fake-final")
            (root / "post-package.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "short-drama-platform-package",
                        "package_id": "short-plate",
                        "intro": {"mode": "short", "duration_sec": 5.0},
                        "outro": {"mode": "none"},
                    }
                ),
                encoding="utf-8",
            )
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["outputs"] = {
                "final_film": {"path": "film_final.mp4", "duration_sec": 1.0, "sha256": "x"}
            }
            (root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            export_composition(root, engine="hyperframes", force=True, layout="underlay")
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="title-sequence"', html)
            self.assertIn('data-duration="0.400"', html)
            self.assertIn('data-caption-clock-offset="0.000"', html)
            self.assertIn('data-duration="1.000"', html)

    @pytest.mark.slow
    def test_ecchi_preset_css_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            # inject rnb mood for auto → but force explicit
            result = export_composition(
                root,
                engine="hyperframes",
                force=True,
                compose_preset="ecchi-rnb",
            )
            self.assertEqual(result["compose_preset"], "ecchi-rnb")
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn("preset: ecchi-rnb", html)
            self.assertIn("rgba(255, 160, 190", html)  # blush border
            self.assertIn('data-compose-preset="ecchi-rnb"', html)

    @pytest.mark.slow
    def test_post_package_owns_episode_cards_and_caption_safe_area(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            (root / "post-package.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "short-drama-platform-package",
                        "package_id": "platform-v1",
                        "intro": {"mode": "short", "duration_sec": 1.1, "subtitle": "EP.01"},
                        "outro": {
                            "mode": "hook",
                            "duration_sec": 2.2,
                            "next_episode": "第 2 集",
                            "cta": "敬请期待",
                        },
                        "captions": {
                            "theme": "platform-drama",
                            "max_chars": 10,
                            "languages": ["zh"],
                        },
                        "safe_area": {"top_pct": 10, "bottom_pct": 20},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            export_composition(root, engine="hyperframes", force=True)
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            receipt = json.loads(
                (root / "compose" / "hyperframes" / "media-stage-receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("EP.01", html)
            self.assertIn('data-duration="1.100"', html)
            self.assertIn("第 2 集", html)
            self.assertIn('data-platform-package="platform-v1"', html)
            self.assertIn('data-caption-theme="platform-drama"', html)
            self.assertIn("rgba(7, 10, 18, 0.78)", html)
            self.assertIn("bottom: 256px", html)  # 20% of vertical 1280 frame
            self.assertEqual(receipt["platform_package"]["package_id"], "platform-v1")
            self.assertEqual(receipt["caption_theme"], "platform-drama")

    @pytest.mark.slow
    def test_show_package_drives_reusable_opening_and_ending_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            (root / "show-package.json").write_text(
                json.dumps(
                    {
                        "id": "vertical-drama.v1",
                        "version": "1.0.0",
                        "brand": {"label": "AI FILM SPACE", "accent": "#F5C2D5"},
                        "opening": {
                            "duration_sec": 1.2,
                            "series_title": "午夜祕密",
                            "episode": "EP.01",
                        },
                        "captions": {"identity": "platform-drama", "safe_bottom_px": 240},
                        "ending": {
                            "duration_sec": 1.8,
                            "cta": "下一集，敬请期待",
                            "next_episode_hook": "门后的声音。",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            export_composition(root, engine="hyperframes", force=True)

            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            manifest = json.loads((root / "compose" / "package.json").read_text(encoding="utf-8"))
            self.assertIn('data-show-package="vertical-drama.v1"', html)
            self.assertIn("午夜祕密", html)
            self.assertIn("下一集，敬请期待", html)
            self.assertEqual(manifest["show_package"]["id"], "vertical-drama.v1")

    @pytest.mark.slow
    def test_post_package_none_modes_do_not_fall_back_to_default_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film_root(root, n_shots=1)
            (root / "post-package.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "short-drama-platform-package",
                        "package_id": "no-cards",
                        "intro": {"mode": "none"},
                        "outro": {"mode": "none"},
                    }
                ),
                encoding="utf-8",
            )
            export_composition(root, engine="hyperframes", force=True)
            html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('id="title-card"', html)
            self.assertNotIn('id="end-card"', html)


if __name__ == "__main__":
    unittest.main()
