from __future__ import annotations

import json
from pathlib import Path

import pytest
from audio_timeline import compile_timeline
from scene_sound_stems import render_scene_sound_stem
from sfx_candidates import approve, attach_to_shot
from sfx_library import (
    audit,
    candidate_asset,
    import_project_asset,
    stage_project_candidate,
    write_candidate_review_pack,
)
from test_sfx_candidates import _pending_candidate


def _approve_legacy(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(root)
    approve(
        root,
        "mmaudio-sfx-1-abc123",
        reviewer="dex",
        heard_full=True,
        sync_confirmed=True,
        no_speech_confirmed=True,
        no_music_confirmed=True,
        artifact_free_confirmed=True,
        asr_speech_reviewed=True,
    )


def test_import_project_asset_creates_one_auditable_global_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, armory = tmp_path / "project", tmp_path / "armory"
    _approve_legacy(monkeypatch, project)

    imported = import_project_asset(project, "mmaudio-sfx-1-abc123", library_root=armory)
    report = audit(library_root=armory)

    assert imported["source"] == "library:sfx/approved-noncommercial/mmaudio-sfx-1-abc123.wav"
    assert report["approved_count"] == 1
    assert report["unique_sha256_count"] == 1
    assert report["invalid"] == []
    assert (armory / "sfx" / "reviews" / "mmaudio-sfx-1-abc123.vibevoice-asr-review.json").is_file()


def test_stage_project_candidate_keeps_reviewable_bytes_in_global_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, armory = tmp_path / "project", tmp_path / "armory"
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(project)

    staged = stage_project_candidate(project, "mmaudio-sfx-1-abc123", library_root=armory)
    wav, receipt, record = candidate_asset(
        "mmaudio-sfx-1-abc123", library_root=armory
    )

    assert staged["source"] == "library:sfx/pending-noncommercial/mmaudio-sfx-1-abc123.wav"
    assert wav.is_file() and receipt.is_file()
    assert record["status"] == "pending_human_review"
    assert record["production_eligible"] is False
    assert audit(library_root=armory)["candidate_count"] == 1


def test_stage_project_candidate_rebinds_asr_evidence_to_global_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, armory = tmp_path / "project", tmp_path / "armory"
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(project, with_asr_screen=True)

    stage_project_candidate(project, "mmaudio-sfx-1-abc123", library_root=armory)
    _, _, record = candidate_asset("mmaudio-sfx-1-abc123", library_root=armory)

    assert record["asr_speech_screen"]["receipt"] == (
        "library:sfx/reviews/candidates/mmaudio-sfx-1-abc123.vibevoice-asr-review.json"
    )
    assert (
        armory
        / "sfx"
        / "reviews"
        / "candidates"
        / "mmaudio-sfx-1-abc123.vibevoice-asr-review.json"
    ).is_file()


def test_candidate_review_pack_uses_global_not_project_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, armory = tmp_path / "project", tmp_path / "armory"
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(project, with_asr_screen=True)
    stage_project_candidate(project, "mmaudio-sfx-1-abc123", library_root=armory)

    pack = write_candidate_review_pack("foundation", library_root=armory)
    content = Path(pack["path"]).read_text(encoding="utf-8")

    assert pack["candidate_count"] == 1
    assert "pending-noncommercial/mmaudio-sfx-1-abc123.wav" in content
    assert str(project) not in content


def test_audit_rejects_tampered_asr_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, armory = tmp_path / "project", tmp_path / "armory"
    _approve_legacy(monkeypatch, project)
    import_project_asset(project, "mmaudio-sfx-1-abc123", library_root=armory)
    review = armory / "sfx" / "reviews" / "mmaudio-sfx-1-abc123.vibevoice-asr-review.json"
    review.write_text('{"changed":true}', encoding="utf-8")

    report = audit(library_root=armory)

    assert report["approved_count"] == 0
    assert report["invalid"] == ["mmaudio-sfx-1-abc123"]


def test_attach_can_reference_global_armory_without_copying_wav(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, film, armory = tmp_path / "project", tmp_path / "film", tmp_path / "armory"
    _approve_legacy(monkeypatch, project)
    import_project_asset(project, "mmaudio-sfx-1-abc123", library_root=armory)
    monkeypatch.setenv("AIFILM_SFX_LIBRARY_ROOT", str(armory))
    (film / "film-spec.json").parent.mkdir(parents=True, exist_ok=True)
    (film / "film-spec.json").write_text(
        json.dumps(
            {
                "delivery_scope": "noncommercial_internal",
                "scenes": [{"id": "s1", "shots": [{"id": "shot01", "duration_sec": 2.0}]}],
            }
        ),
        encoding="utf-8",
    )

    attached = attach_to_shot(
        film,
        "mmaudio-sfx-1-abc123",
        shot_id="shot01",
        kind="foley",
        start_offset_sec=0,
        duration_sec=1,
        material="wood",
        noncommercial_internal_ok=True,
    )

    cue = attached["cue"]
    assert cue["source"].startswith("library:")
    assert cue["approval_receipt"].startswith("library:")
    assert (
        not list((film / "audio" / "candidates").rglob("*.wav"))
        if (film / "audio" / "candidates").exists()
        else True
    )
    timeline = compile_timeline(json.loads((film / "film-spec.json").read_text()), root=film)
    assert timeline["events"][0]["source"] == cue["source"]
    result = render_scene_sound_stem(
        film,
        timeline,
        duration_sec=2,
        out=film / "audio" / "scene.wav",
        sample_rate=8000,
    )
    assert result["event_count"] == 1
