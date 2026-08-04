"""True-video-only hero policy — stills / Ken Burns never enter drama timeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from true_video_policy import (  # noqa: E402
    CODE_FORBIDDEN_ENDPOINT,
    CODE_PANEL_NOT_HERO,
    CODE_STILL_AS_CLIP,
    TrueVideoPolicyError,
    assert_hero_clip_source,
    is_panel_project,
    path_looks_like_still,
    scan_manifest_true_video,
    source_blob_forbidden,
)


def test_still_suffix_detected() -> None:
    assert path_looks_like_still("/x/shot01.png")
    assert path_looks_like_still("a.JPG")
    assert not path_looks_like_still("/x/shot01.mp4")


def test_source_blob_forbids_ken_burns_and_panel() -> None:
    assert source_blob_forbidden("ken_burns_plate.mp4")
    assert source_blob_forbidden("clip.mp4", tags=["ken_burns"])
    assert source_blob_forbidden("clip.mp4", tags=["panel_animation"])
    assert source_blob_forbidden("clip.mp4", provider="shortform_motion")
    assert not source_blob_forbidden("clip.mp4", endpoint="image_to_video")


def test_assert_rejects_png_as_hero(tmp_path: Path) -> None:
    still = tmp_path / "s01.png"
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    with pytest.raises(TrueVideoPolicyError) as ei:
        assert_hero_clip_source(
            still,
            endpoint="image_to_video",
            status="approved",
            root=tmp_path,
            role="hero",
        )
    assert CODE_STILL_AS_CLIP in str(ei.value) or "still" in str(ei.value).lower()


def test_assert_rejects_ken_burns_endpoint(tmp_path: Path) -> None:
    clip = tmp_path / "fake.mp4"
    clip.write_bytes(b"\x00" * 64)
    with pytest.raises(TrueVideoPolicyError) as ei:
        assert_hero_clip_source(
            clip,
            endpoint="ken_burns",
            status="approved",
            root=tmp_path,
            role="hero",
        )
    assert CODE_FORBIDDEN_ENDPOINT in str(ei.value) or "ken" in str(ei.value).lower()


def test_assert_rejects_panel_tags_on_drama(tmp_path: Path) -> None:
    clip = tmp_path / "p.mp4"
    clip.write_bytes(b"\x00" * 64)
    (tmp_path / "film-spec.json").write_text(
        '{"production_mode":"dialogue_drama"}', encoding="utf-8"
    )
    with pytest.raises(TrueVideoPolicyError) as ei:
        assert_hero_clip_source(
            clip,
            endpoint="image_to_video",
            status="approved",
            tags=["panel_animation"],
            root=tmp_path,
            role="hero",
        )
    assert CODE_PANEL_NOT_HERO in str(ei.value) or "panel" in str(ei.value).lower()


def test_panel_project_allows_panel_mode(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        '{"production_mode":"panel"}', encoding="utf-8"
    )
    assert is_panel_project(tmp_path) is True


def test_drama_default_not_panel(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    assert is_panel_project(tmp_path) is False


def test_scan_manifest_flags_still_path(tmp_path: Path) -> None:
    still = tmp_path / "clips" / "s01.png"
    still.parent.mkdir(parents=True)
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (tmp_path / "manifest.json").write_text(
        """
        {
          "clips": {
            "s01": {
              "status": "approved",
              "path": "%s",
              "source_endpoint": "image_to_video",
              "identity_approved": true,
              "motion_approved": true,
              "review_note": "ok"
            }
          }
        }
        """.replace("%s", str(still).replace("\\", "\\\\")),
        encoding="utf-8",
    )
    (tmp_path / "film-spec.json").write_text(
        '{"scenes":[{"shots":[{"id":"s01"}]}]}', encoding="utf-8"
    )
    rep = scan_manifest_true_video(tmp_path)
    assert rep["ok"] is False
    assert rep["checked"] == 1
    assert any(v.get("shot_id") == "s01" for v in rep["violations"])


def test_assert_accepts_clean_i2v_mp4(tmp_path: Path) -> None:
    clip = tmp_path / "good.mp4"
    clip.write_bytes(b"\x00" * 64)
    (tmp_path / "film-spec.json").write_text(
        '{"production_mode":"dialogue_drama"}', encoding="utf-8"
    )
    rep = assert_hero_clip_source(
        clip,
        endpoint="image_to_video",
        status="approved",
        root=tmp_path,
        role="hero",
    )
    assert rep["ok"] is True


def test_external_requires_generative_tags(tmp_path: Path) -> None:
    clip = tmp_path / "ext.mp4"
    clip.write_bytes(b"\x00" * 64)
    with pytest.raises(TrueVideoPolicyError):
        assert_hero_clip_source(
            clip,
            endpoint="external",
            status="approved",
            root=tmp_path,
            role="hero",
        )
    rep = assert_hero_clip_source(
        clip,
        endpoint="external",
        status="approved",
        tags=["generated_i2v", "grok"],
        root=tmp_path,
        role="hero",
    )
    assert rep["ok"] is True


def test_motion_plan_blocked_on_drama(tmp_path: Path) -> None:
    from motion_plan import MotionPlanError, build_motion_plan

    (tmp_path / "film-spec.json").write_text(
        """
        {
          "production_mode": "dialogue_drama",
          "scenes": [{"shots": [{"id": "shot01", "dsl": {"motion": "ken_burns"}}]}]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(MotionPlanError) as ei:
        build_motion_plan(tmp_path, "shot01")
    assert "forbidden" in str(ei.value).lower() or "panel" in str(ei.value).lower()
