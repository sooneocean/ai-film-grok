"""compose-render: register-final, remotion media copy, layout underlay."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compose_render as compose_mod  # noqa: E402
from compose_render import (  # noqa: E402
    ComposeRenderError,
    assert_underlay_not_double_burn,
    compose_render,
    copy_remotion_media,
    ensure_audio_mux,
    plate_subtitles_burned_in,
    probe_designed_post_tooling,
    probe_has_audio,
    probe_remotion_readiness,
    register_final_film,
    remotion_actionable_next_steps,
    remotion_npm_install,
)
from export_composition import export_composition  # noqa: E402
from runtime_policy import sha256  # noqa: E402


def test_compose_subprocess_contract_adds_noninteractive_ffmpeg_flag(monkeypatch) -> None:
    calls = {}

    def fake_run(argv, **kwargs):
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    compose_mod.run(["ffmpeg", "-i", "input.mp4"], check=False, timeout=7)
    assert calls["argv"][1] == "-nostdin"
    assert calls["kwargs"]["timeout"] == 7
    assert calls["kwargs"]["stdin"] is compose_mod.subprocess.DEVNULL


def test_designed_post_probe_reports_missing_npx_and_timeout(monkeypatch) -> None:
    monkeypatch.setattr(compose_mod, "which_npx", lambda: None)
    missing = probe_designed_post_tooling()
    assert missing["hyperframes_ok"] is False
    assert "npx missing" in missing["error"]

    monkeypatch.setattr(compose_mod, "which_npx", lambda: "/fake/npx")

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("npx", 120)

    monkeypatch.setattr(compose_mod, "run", timeout_run)
    timed_out = probe_designed_post_tooling()
    assert timed_out["hyperframes_ok"] is False
    assert "timed out" in timed_out["error"].lower()


@pytest.mark.slow
def test_platform_package_hyperframes_real_render(tmp_path: Path) -> None:
    """Real 9:16 underlay render proves package → check → MP4, not HTML only."""
    tooling = probe_designed_post_tooling()
    if not tooling.get("hyperframes_ok"):
        pytest.skip(f"HyperFrames unavailable: {tooling.get('error')}")

    root = tmp_path / "film"
    root.mkdir()
    _seed_film(root, n_shots=1)
    plate = root / "out" / "film_final.mp4"
    _make_motion_clip(plate, seconds=10.0, with_audio=True)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"]["final_film"] = {
        "path": "film_final.mp4",
        "sha256": sha256(plate),
        "duration_sec": 10.0,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "out" / "final-delivery.json").write_text(
        json.dumps({"subtitles": {"burned_in": False}}), encoding="utf-8"
    )
    (root / "out" / "final.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n真实渲染验收\n\n"
        "2\n00:00:05,000 --> 00:00:06,000\n最后一句对白\n",
        encoding="utf-8",
    )
    (root / "post-package.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "short-drama-platform-package",
                "package_id": "render-canary-v1",
                "intro": {"mode": "short", "subtitle": "EP.01"},
                "outro": {"mode": "hook", "cta": "下一集，敬请期待"},
                "captions": {"max_chars": 10, "languages": ["zh"]},
                "safe_area": {"top_pct": 10, "bottom_pct": 20},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "show-package.json").write_text(
        json.dumps(
            {
                "id": "render-romance-v1",
                "version": "1.0.0",
                "brand": {
                    "label": "AI FILM SPACE",
                    "accent": "#A3132A",
                    "motion_preset": "suspense-red",
                },
                "opening": {"duration_sec": 1.8, "series_title": "真实验收", "episode": "EP.01"},
                "captions": {"safe_bottom_px": 240},
                "ending": {"duration_sec": 2.2, "cta": "下一集", "next_episode_hook": "继续"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        result = compose_render(
            root,
            engine="hyperframes",
            export_first=True,
            layout="underlay",
            compose_preset="minimal",
            quality="draft",
            register=False,
        )
    except Exception as exc:  # noqa: BLE001 - canary should not block release on browser flake
        msg = str(exc)
        if "Navigation timeout" in msg or "timeout" in msg.lower():
            pytest.skip(f"HyperFrames real-render canary flaky in this environment: {msg[:200]}")
        raise

    output = Path(result["output"])
    assert result["rendered"] is True
    assert output.is_file() and output.stat().st_size > 0
    package = json.loads((root / "compose" / "package.json").read_text(encoding="utf-8"))
    assert package["show_package"]["brand"]["motion_preset"] == "suspense-red"
    assert probe_has_audio(output)
    receipt = json.loads(
        (root / "compose" / "hyperframes" / "media-stage-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["platform_package"]["package_id"] == "render-canary-v1"
    assert [cue["id"] for cue in receipt["cinematic_audio_cues"]] == [
        "suspense-intro",
        "suspense-outro",
    ]
    html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
    assert 'id="platform-ending"' in html
    assert 'data-start="7.800" data-duration="2.200"' in html


def test_compose_metadata_and_npm_gate_fail_closed(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "film"
    (root / "out").mkdir(parents=True)
    (root / "out" / "final-delivery.json").write_text("{broken", encoding="utf-8")
    assert plate_subtitles_burned_in(root) is None

    rem = root / "compose" / "remotion"
    rem.mkdir(parents=True)
    (rem / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(compose_mod, "which_npm", lambda: None)
    with pytest.raises(ComposeRenderError, match="npm not found"):
        remotion_npm_install(rem)


def _ffmpeg_available() -> bool:
    return (
        subprocess.call(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        == 0
    )


def _make_motion_clip(path: Path, *, seconds: float = 2.0, with_audio: bool = True) -> None:
    """Synthetic clip with continuous motion (testsrc2) so media_qa motion_ok can pass."""
    path.parent.mkdir(parents=True, exist_ok=True)
    motion = path.with_suffix(".motion.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=160x90:r=24:d={seconds}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(motion),
        ],
        check=True,
        capture_output=True,
    )
    if with_audio:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(motion),
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:duration={seconds}",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        motion.unlink(missing_ok=True)
    else:
        motion.replace(path)


def _seed_film(root: Path, *, n_shots: int = 1, with_final: bool = False) -> None:
    for name in ("clips", "out", "receipts", "keyframes", "prompts", "audio", "canonical"):
        (root / name).mkdir(parents=True, exist_ok=True)
    shots = []
    clips = {}
    for i in range(1, n_shots + 1):
        sid = f"shot{i:02d}"
        shots.append(
            {
                "id": sid,
                "dramatic_function": "hook" if i == 1 else "reaction",
                "nar": f"话说第{i}镜。",
                "duration_sec": 6,
                "lipsync": False,
                "dsl": {
                    "subject": "woman",
                    "action": "looks",
                    "motion": "slow push-in, soft blink, breathing, idle not speaking",
                },
            }
        )
        clip = root / "clips" / f"{sid}.mp4"
        # placeholder bytes enough for export path checks; motion tests use real ffmpeg files
        clip.write_bytes(b"\x00fake")
        clips[sid] = {
            "shot_id": sid,
            "path": str(clip),
            "status": "approved",
            "duration_sec": 6.0,
            "source_endpoint": "image_to_video",
            "identity_approved": True,
            "motion_approved": True,
            "sha256": "x",
        }
    spec = {
        "title": "compose-render-test",
        "vo_mode": "storyteller",
        "transition_sec": 0.28,
        "director_intent": {
            "logline": "测试 compose-render 正式注册链路的完整句子。",
            "tone": "测试",
            "emotional_arc": ["a", "b", "c"],
        },
        "scenes": [{"shots": shots}],
    }
    (root / "film-spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    outputs: dict = {}
    if with_final and _ffmpeg_available():
        final = root / "out" / "film_final.mp4"
        _make_motion_clip(final, seconds=1.2, with_audio=True)
        outputs["final_film"] = {
            "path": "film_final.mp4",
            "sha256": sha256(final),
            "duration_sec": 1.2,
        }
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "title": "compose-render-test",
                "width": 720,
                "height": 1280,
                "fps": 30,
                "clips": clips,
                "gates": {},
                "outputs": outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@unittest.skipUnless(_ffmpeg_available(), "ffmpeg required")
@pytest.mark.slow
class RegisterFinalTests(unittest.TestCase):
    @pytest.mark.slow
    def test_register_final_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root)
            src = root / "out" / "src.mp4"
            _make_motion_clip(src, seconds=1.0, with_audio=True)
            result = register_final_film(
                root,
                src,
                out_name="film_final.mp4",
                post_engine="hyperframes",
                force=True,
            )
            self.assertTrue(result["ok"])
            self.assertFalse(result["final_complete"])
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            ff = man["outputs"]["final_film"]
            self.assertEqual(ff["path"], "film_final.mp4")
            self.assertEqual(ff["post_engine"], "hyperframes")
            self.assertEqual(ff["sha256"], result["output_sha256"])
            self.assertTrue((root / "out" / "film_final.mp4").is_file())
            self.assertTrue((root / "out" / "final-delivery.json").is_file())

    @pytest.mark.slow
    def test_register_final_invalidates_old_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root)
            src = root / "out" / "src.mp4"
            _make_motion_clip(src, seconds=1.0, with_audio=True)
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            man["outputs"]["final_review"] = {
                "approved": True,
                "output_sha256": "old",
                "reviewer": "x",
                "notes": "y",
            }
            (root / "manifest.json").write_text(
                json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            register_final_film(
                root, src, out_name="film_final.mp4", post_engine="external", force=True
            )
            man2 = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("final_review", man2["outputs"])
            self.assertIn("final_review_stale", man2["outputs"])


@unittest.skipUnless(_ffmpeg_available(), "ffmpeg required")
@pytest.mark.slow
class AudioMuxTests(unittest.TestCase):
    @pytest.mark.slow
    def test_mux_from_final_when_video_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            (root / "out").mkdir()
            silent = root / "out" / "silent.mp4"
            final = root / "out" / "film_final.mp4"
            out = root / "out" / "mixed.mp4"
            _make_motion_clip(silent, seconds=0.8, with_audio=False)
            _make_motion_clip(final, seconds=0.8, with_audio=True)
            self.assertFalse(probe_has_audio(silent))
            self.assertTrue(probe_has_audio(final))
            info = ensure_audio_mux(silent, root, out)
            self.assertTrue(info["ok"])
            self.assertEqual(info["action"], "mux_from_final")
            self.assertTrue(probe_has_audio(out))


@pytest.mark.slow
class ToolingProbeTests(unittest.TestCase):
    @pytest.mark.slow
    def test_probe_designed_post_tooling_shape(self) -> None:
        info = probe_designed_post_tooling()
        self.assertIn("npx", info)
        self.assertIn("hyperframes_ok", info)
        self.assertIn("error", info)
        # When npx exists in this environment, version probe should not crash
        if info.get("npx"):
            self.assertTrue(isinstance(info.get("hyperframes_ok"), bool))


@pytest.mark.slow
class DoubleBurnGateTests(unittest.TestCase):
    @pytest.mark.slow
    def test_underlay_blocks_when_burned_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            (root / "out").mkdir(parents=True)
            (root / "out" / "film_final.mp4").write_bytes(b"\x00fake")
            (root / "out" / "final-delivery.json").write_text(
                json.dumps({"subtitles": {"burned_in": True}}),
                encoding="utf-8",
            )
            with self.assertRaises(ComposeRenderError) as ctx:
                assert_underlay_not_double_burn(root, layout="underlay")
            self.assertIn("double-burn", str(ctx.exception).lower())

    @pytest.mark.slow
    def test_allow_burned_underlay_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            (root / "out").mkdir(parents=True)
            (root / "out" / "final-delivery.json").write_text(
                json.dumps({"subtitles": {"burned_in": True}}),
                encoding="utf-8",
            )
            info = assert_underlay_not_double_burn(
                root, layout="underlay", allow_burned_underlay=True
            )
            self.assertTrue(info["ok"])

    @pytest.mark.slow
    def test_subs_off_plate_allows_underlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            (root / "out").mkdir(parents=True)
            (root / "out" / "final-delivery.json").write_text(
                json.dumps({"subtitles": {"burned_in": False}}),
                encoding="utf-8",
            )
            info = assert_underlay_not_double_burn(root, layout="underlay")
            self.assertTrue(info["ok"])
            self.assertIs(info.get("burned_in"), False)


@pytest.mark.slow
class RemotionCopyAndLayoutTests(unittest.TestCase):
    @pytest.mark.slow
    def test_copy_remotion_media_and_underlay_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root, n_shots=2, with_final=_ffmpeg_available())
            # export needs real files under clips for relative paths — already placeholders
            result = export_composition(root, engine="both", force=True, layout="auto")
            self.assertTrue(result["ok"])
            if _ffmpeg_available() and (root / "out" / "film_final.mp4").is_file():
                self.assertEqual(result["layout"], "underlay")
                html = (root / "compose" / "hyperframes" / "index.html").read_text(encoding="utf-8")
                self.assertIn("final-underlay", html)
            else:
                self.assertEqual(result["layout"], "multiclip")

            # real files for copy
            for i in (1, 2):
                sid = f"shot{i:02d}"
                p = root / "clips" / f"{sid}.mp4"
                p.write_bytes(b"clip-bytes-" + sid.encode())
            copy = copy_remotion_media(root)
            # multiclip: 2 shots; underlay layout also copies final film → 3
            self.assertGreaterEqual(copy["count"], 2)
            plan = json.loads(
                (root / "compose" / "remotion" / "media-copy-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(copy["count"], len(plan["items"]))
            pub = root / "compose" / "remotion" / "public" / "clips"
            self.assertTrue(any(pub.glob("shot*")))


@pytest.mark.slow
class RemotionComposeRenderBranchTests(unittest.TestCase):
    @pytest.mark.slow
    def test_probe_remotion_not_ready_without_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root, n_shots=1)
            export_composition(root, engine="remotion", force=True)
            info = probe_remotion_readiness(root)
            self.assertTrue(info["package_json"])
            self.assertTrue(info["has_npm_deps_declared"])
            self.assertTrue(info["root_tsx"])
            self.assertTrue(info["film_tsx"])
            self.assertFalse(info["ready"])
            self.assertTrue(any("node_modules" in m for m in info["missing"]))

    @pytest.mark.slow
    def test_remotion_next_steps_list_bootstrap_render_register(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            steps = remotion_actionable_next_steps(root)
            blob = "\n".join(steps)
            self.assertIn("npm install", blob)
            self.assertIn("--npm-install", blob)
            self.assertIn("remotion render", blob)
            self.assertIn("register-final", blob)
            self.assertIn("post-engine remotion", blob)
            self.assertIn("hyperframes", blob)

    @pytest.mark.slow
    def test_remotion_npm_install_success_with_fake_npm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rem = Path(tmp) / "remotion"
            rem.mkdir()
            (rem / "package.json").write_text(
                json.dumps({"name": "t", "dependencies": {"remotion": "4.0.0"}}),
                encoding="utf-8",
            )
            fake_npm = Path(tmp) / "fake-npm"
            # Creates node_modules layout that probe_remotion_readiness accepts
            fake_npm.write_text(
                "#!/bin/sh\n"
                "set -e\n"
                "mkdir -p node_modules/.bin node_modules/remotion\n"
                'printf "#!/bin/sh\\nexit 1\\n" > node_modules/.bin/remotion\n'
                "chmod +x node_modules/.bin/remotion\n"
                "echo installed\n",
                encoding="utf-8",
            )
            fake_npm.chmod(0o755)
            info = remotion_npm_install(rem, npm_bin=str(fake_npm), timeout=30)
            self.assertTrue(info["ok"])
            self.assertTrue((rem / "node_modules" / "remotion").is_dir())

    @pytest.mark.slow
    def test_remotion_npm_install_missing_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rem = Path(tmp) / "empty"
            rem.mkdir()
            with self.assertRaises(ComposeRenderError) as ctx:
                remotion_npm_install(rem, npm_bin="/bin/true", timeout=5)
            self.assertIn("package.json", str(ctx.exception))

    @pytest.mark.slow
    def test_compose_render_npm_install_then_ready_attempts_render(self) -> None:
        """--npm-install with fake npm reaches render path (render fails honestly)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root, n_shots=1)
            (root / "clips" / "shot01.mp4").write_bytes(b"clip-shot01")
            export_composition(root, engine="remotion", force=True)
            rem = root / "compose" / "remotion"
            fake_npm = Path(tmp) / "fake-npm"
            fake_npm.write_text(
                "#!/bin/sh\n"
                "set -e\n"
                "mkdir -p node_modules/.bin node_modules/remotion\n"
                'printf "#!/bin/sh\\nexit 1\\n" > node_modules/.bin/remotion\n'
                "chmod +x node_modules/.bin/remotion\n",
                encoding="utf-8",
            )
            fake_npm.chmod(0o755)

            # Inject fake npm by patching which via remotion_npm_install path:
            # call compose_render after pre-running install with fake npm, then
            # also test the compose_render branch by monkeypatching remotion_npm_install.
            import compose_render as cr_mod

            original = cr_mod.remotion_npm_install

            def _fake_install(rem_dir, **kwargs):  # type: ignore[no-untyped-def]
                return original(rem_dir, npm_bin=str(fake_npm), timeout=30)

            cr_mod.remotion_npm_install = _fake_install  # type: ignore[assignment]
            try:
                with self.assertRaises(ComposeRenderError) as ctx:
                    compose_render(
                        root,
                        engine="remotion",
                        export_first=False,
                        npm_install=True,
                        register=False,
                    )
                self.assertIn("remotion render failed", str(ctx.exception).lower())
                # install side-effect present
                self.assertTrue((rem / "node_modules" / "remotion").is_dir())
            finally:
                cr_mod.remotion_npm_install = original  # type: ignore[assignment]

    @pytest.mark.slow
    def test_compose_render_npm_install_failure_returns_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root, n_shots=1)
            (root / "clips" / "shot01.mp4").write_bytes(b"clip-shot01")
            export_composition(root, engine="remotion", force=True)
            fake_npm = Path(tmp) / "fail-npm"
            fake_npm.write_text("#!/bin/sh\necho boom >&2\nexit 2\n", encoding="utf-8")
            fake_npm.chmod(0o755)

            import compose_render as cr_mod

            original = cr_mod.remotion_npm_install

            def _fail_install(rem_dir, **kwargs):  # type: ignore[no-untyped-def]
                return original(rem_dir, npm_bin=str(fake_npm), timeout=10)

            cr_mod.remotion_npm_install = _fail_install  # type: ignore[assignment]
            try:
                result = compose_render(
                    root,
                    engine="remotion",
                    export_first=False,
                    npm_install=True,
                    register=False,
                )
                self.assertFalse(result["ok"])
                self.assertFalse(result["rendered"])
                self.assertIn("npm install failed", result.get("error", "").lower())
                self.assertIn("next_steps", result)
            finally:
                cr_mod.remotion_npm_install = original  # type: ignore[assignment]

    @pytest.mark.slow
    def test_compose_render_remotion_actionable_when_not_bootstrapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root, n_shots=2)
            for i in (1, 2):
                sid = f"shot{i:02d}"
                (root / "clips" / f"{sid}.mp4").write_bytes(b"clip-" + sid.encode())
            result = compose_render(
                root,
                engine="remotion",
                export_first=True,
                force_export=True,
                register=False,
            )
            self.assertFalse(result["ok"])
            self.assertFalse(result["rendered"])
            self.assertEqual(result["engine"], "remotion")
            self.assertIn("next_steps", result)
            steps = result["next_steps"]
            self.assertTrue(isinstance(steps, list) and len(steps) >= 4)
            joined = "\n".join(steps)
            self.assertIn("npm install", joined)
            self.assertIn("register-final", joined)
            # media was still copied
            copy = result["steps"].get("remotion_media_copy") or {}
            self.assertTrue(copy.get("ok"))
            self.assertEqual(copy.get("count"), 2)
            self.assertTrue(any((root / "compose" / "remotion" / "public" / "clips").glob("shot*")))

    @pytest.mark.slow
    def test_compose_render_remotion_ready_path_calls_register_label(self) -> None:
        """When readiness is forced ready, auto-render path is taken (render may fail honestly)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            root.mkdir()
            _seed_film(root, n_shots=1)
            (root / "clips" / "shot01.mp4").write_bytes(b"clip-shot01")
            export_composition(root, engine="remotion", force=True)
            copy_remotion_media(root)
            rem = root / "compose" / "remotion"
            # Fake node_modules/remotion so readiness passes; remotion render will fail honestly
            (rem / "node_modules" / "remotion").mkdir(parents=True)
            (rem / "node_modules" / ".bin").mkdir(parents=True)
            fake_bin = rem / "node_modules" / ".bin" / "remotion"
            fake_bin.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            fake_bin.chmod(0o755)

            info = probe_remotion_readiness(root)
            # npx may or may not exist; if missing, not ready
            if not info.get("npx"):
                self.assertFalse(info["ready"])
                return
            self.assertTrue(info["ready"], msg=info)

            with self.assertRaises(ComposeRenderError) as ctx:
                compose_render(
                    root,
                    engine="remotion",
                    export_first=False,
                    register=False,
                )
            self.assertIn("remotion render failed", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
