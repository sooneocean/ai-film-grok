from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from shortform_director import (  # noqa: E402
    ShortformError,
    aroll_broll,
    create_package,
    enable_lipsync,
    render_lipsync,
    review,
    segment_aroll_words,
    validate_package,
)
from shortform_motion import ShortformMotionError, build_plan, render_plan  # noqa: E402


def _write(root: Path, name: str, content: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _png(root: Path, name: str, color: tuple[int, int, int, int]) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (64, 64), color).save(path)
    return path


def test_topic_package_is_provider_neutral_and_requires_two_reviews() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = _write(root, "approved.txt", b"A sharp hook. Then the proof arrives.")
        package = create_package(root, mode="topic", approved_script=script)
        assert package["provider_policy"]["atlas_cloud"] == "disabled"
        assert len(package["beats"][0]["shots"]) == 2
        assert not validate_package(root, require_approved=True)["ok"]
        review(root, stage="plan", reviewer="dex", note="timing works", approve=True)
        review(root, stage="sample", reviewer="dex", note="candidate works", approve=True)
        assert validate_package(root, require_approved=True)["ok"]


def test_aroll_segments_at_word_boundaries_and_never_allows_new_lipsync() -> None:
    words = [
        {"start": 0.0, "end": 1.0, "text": "One"},
        {"start": 1.1, "end": 2.0, "text": "long"},
        {"start": 2.1, "end": 3.0, "text": "sentence"},
        {"start": 3.5, "end": 4.5, "text": "continues"},
        {"start": 4.6, "end": 5.5, "text": "here."},
        {"start": 6.0, "end": 7.0, "text": "Second"},
        {"start": 7.1, "end": 8.0, "text": "sentence."},
    ]
    segments = segment_aroll_words(words)
    assert segments[0]["start_sec"] == 0.0
    assert segments[-1]["end_sec"] == 8.0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        video = _write(root, "source.mp4", b"not-decoded-in-plan")
        transcript = _write(root, "transcript.json", json.dumps({"words": words}).encode())
        with mock.patch("shortform_director._duration", return_value=8.0):
            package = create_package(root, mode="aroll", source_video=video, transcript=transcript)
        assert package["source"]["audio_policy"] == "source_audio_is_lipsync_truth"
        with pytest.raises(ShortformError, match="cannot enable"):
            enable_lipsync(
                root, shot_id="beat01_a", speaker="x", face_target="x", audio_sha256="a" * 64
            )
        assert aroll_broll(root, beat_id="beat01")[0]["audio_policy"] == "carry_parent_dialogue"


def test_croll_anchor_hash_and_lipsync_shape_are_enforced() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = _write(root, "approved.txt", b"A character speaks to camera.")
        anchor = _write(root, "anchor.png", b"approved-anchor")
        create_package(root, mode="croll", approved_script=script, anchor=anchor)
        review(root, stage="plan", reviewer="dex", note="plan", approve=True)
        review(root, stage="sample", reviewer="dex", note="sample", approve=True)
        enable_lipsync(
            root, shot_id="beat01_a", speaker="hero", face_target="hero", audio_sha256="b" * 64
        )
        assert not validate_package(root, require_approved=True)["ok"]
        assert validate_package(root)["ok"]
        anchor.write_bytes(b"changed")
        report = validate_package(root)
        assert not report["ok"]
        assert any("anchor" in item for item in report["issues"])


def test_motion_plan_binds_base_and_layers_and_rejects_escape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = _write(root, "assets/base.png", b"base")
        layer = _write(root, "assets/layer.png", b"layer")
        plan = build_plan(
            root,
            base=base,
            layers=[{"id": "hero", "path": str(layer), "entrance": "fly_in"}],
            shot_id="beat01_a",
        )
        assert plan["base"]["sha256"] == hashlib.sha256(b"base").hexdigest()
        assert plan["backdrop_policy"].startswith("base_with_local_blur")
        with pytest.raises(ShortformMotionError, match="inside root"):
            build_plan(root, base=Path("/tmp/outside.png"), layers=[], shot_id="bad")
        with pytest.raises(ShortformMotionError, match="safe filename"):
            build_plan(root, base=base, layers=[], shot_id="../../../escape")


def test_motion_render_is_hash_bound_decodable_and_reopens_sample_review() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg unavailable")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = _write(root, "approved.txt", b"A character speaks to camera.")
        anchor = _png(root, "anchor.png", (0, 0, 0, 255))
        base = _png(root, "assets/base.png", (30, 50, 120, 255))
        layer = _png(root, "assets/layer.png", (240, 120, 30, 180))
        create_package(root, mode="croll", approved_script=script, anchor=anchor)
        review(root, stage="plan", reviewer="dex", note="plan", approve=True)
        plan = build_plan(
            root,
            base=base,
            layers=[{"id": "hero", "path": str(layer), "entrance": "pop_settle", "scale": 0.4}],
            shot_id="beat01_a",
        )
        result = render_plan(root, plan=Path(plan["path"]), duration_sec=1.0, width=256, height=256)
        candidate = root / result["candidate"]["path"]
        assert candidate.is_file()
        assert result["candidate"]["status"] == "pending_human_review"
        assert not validate_package(root, require_approved=True)["ok"]
        base.write_bytes(b"changed")
        with pytest.raises(ShortformMotionError, match="hash changed"):
            render_plan(root, plan=Path(plan["path"]), duration_sec=1.0, width=256, height=256)


def test_motion_render_rejects_a_symlinked_input_parent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        real = root / "real"
        real.mkdir()
        base = _write(root, "real/base.png", b"base")
        linked = root / "linked"
        linked.symlink_to(real, target_is_directory=True)
        with pytest.raises(ShortformMotionError, match="symlinked path component"):
            build_plan(root, base=linked / base.name, layers=[], shot_id="beat01_a")


def test_relative_evidence_uses_realpath_for_macos_var_aliases() -> None:
    from shortform_director import _relative

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = _write(root, "out.mp4", b"candidate")
        assert _relative(root.resolve(), output) == "out.mp4"


def test_package_rejects_symlinked_source_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = _write(root, "target.txt", b"approved")
        linked = root / "linked.txt"
        linked.symlink_to(target)
        with pytest.raises(ShortformError, match="symlink"):
            create_package(root, mode="topic", approved_script=linked)


def test_aroll_rejects_candidate_with_a_shorter_visual_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shortform_director

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        video = _write(root, "source.mp4", b"source")
        transcript = _write(
            root,
            "transcript.json",
            json.dumps({"words": [{"start": 0, "end": 7, "text": "line."}]}).encode(),
        )
        with mock.patch("shortform_director._duration", side_effect=[7.0, 6.0]):
            create_package(root, mode="aroll", source_video=video, transcript=transcript)
            review(root, stage="plan", reviewer="dex", note="plan", approve=True)
            review(root, stage="sample", reviewer="dex", note="sample", approve=True)
            visuals = root / "visuals"
            visuals.mkdir()
            _write(root, "visuals/beat01.mp4", b"visual")
            monkeypatch.setattr(shortform_director.shutil, "which", lambda _: "/bin/true")
            with pytest.raises(ShortformError, match="shorter than its source beat"):
                shortform_director.assemble_aroll(root, visual_dir=visuals)


def test_explicit_lipsync_render_is_hash_bound_and_requires_new_sample_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = _write(root, "approved.txt", b"A character speaks to camera.")
        anchor = _write(root, "anchor.png", b"approved-anchor")
        video = _write(root, "plate.mp4", b"video")
        audio = _write(root, "line.wav", b"audio")
        create_package(root, mode="croll", approved_script=script, anchor=anchor)
        review(root, stage="plan", reviewer="dex", note="plan", approve=True)
        enable_lipsync(
            root,
            shot_id="beat01_a",
            speaker="hero",
            face_target="hero",
            audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
        )

        class FakeLipSyncError(RuntimeError):
            pass

        def fake_lipsync_one(**kwargs: object) -> dict[str, object]:
            out = kwargs["out"]
            assert isinstance(out, Path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"candidate")
            return {"ok": True, "chosen_backend": "latentsync"}

        fake_module = type(
            "FakeModule",
            (),
            {"LipSyncError": FakeLipSyncError, "lipsync_one": fake_lipsync_one},
        )
        monkeypatch.setitem(sys.modules, "lipsync_backend", fake_module)
        result = render_lipsync(root, shot_id="beat01_a", video=video, audio=audio)
        assert result["candidate"]["backend"] == "latentsync"
        assert result["candidate"]["status"] == "pending_human_review"
        assert not validate_package(root, require_approved=True)["ok"]


def test_lipsync_render_rejects_a_symlinked_default_candidate_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = _write(root, "approved.txt", b"A character speaks to camera.")
        anchor = _write(root, "anchor.png", b"approved-anchor")
        video = _write(root, "plate.mp4", b"video")
        audio = _write(root, "line.wav", b"audio")
        create_package(root, mode="croll", approved_script=script, anchor=anchor)
        review(root, stage="plan", reviewer="dex", note="plan", approve=True)
        enable_lipsync(
            root,
            shot_id="beat01_a",
            speaker="hero",
            face_target="hero",
            audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
        )
        outside = root.parent / "outside-candidates"
        outside.mkdir(exist_ok=True)
        (root / "candidates").symlink_to(outside, target_is_directory=True)
        called = False

        def fake_lipsync_one(**_kwargs: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"ok": True}

        fake_module = type(
            "FakeModule", (), {"LipSyncError": RuntimeError, "lipsync_one": fake_lipsync_one}
        )
        monkeypatch.setitem(sys.modules, "lipsync_backend", fake_module)
        with pytest.raises(ShortformError, match="parent must not be a symlink"):
            render_lipsync(root, shot_id="beat01_a", video=video, audio=audio)
        assert not called
