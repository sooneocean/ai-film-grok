from __future__ import annotations

import hashlib
import json
import math
import wave
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from aifilm_grok import _commit_selected_bgm_usage, build_parser, cmd_init
from bgm_library import approve_candidate, stage_candidate
from cli_bgm_library import cmd_bgm_library
from render_final import RenderError, render_music_template_timeline


def _wav(path: Path, frequency: float = 220.0, duration: float = 1.0) -> Path:
    rate = 44100
    t = np.arange(int(rate * duration), dtype=np.float64)
    signal = np.sin(2.0 * math.pi * frequency * t / rate) * 0.25
    stereo = np.column_stack((signal, signal))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((stereo * 32767).astype("<i2").tobytes())
    return path


def _asset(
    library: Path,
    source: Path,
    *,
    keyscale: str = "A minor",
    bpm: int = 72,
    edit_variant: str = "",
    parent_asset_id: str | None = None,
    transition_to_asset_id: str | None = None,
) -> dict[str, object]:
    recipe = {
        "mood": "rnb",
        "dramatic_tags": ["relationship"],
        "energy": 0.5,
        "stem_profile": "pad",
        "keyscale": keyscale,
        "bpm": bpm,
        "edit_variant": edit_variant,
        "parent_asset_id": parent_asset_id,
        "transition_to_asset_id": transition_to_asset_id,
    }
    staged = stage_candidate(
        library,
        source,
        {
            "mood": "rnb",
            "seed": 7,
            "model": "ACE-Step-1.5",
            "checkpoint_fingerprint": "test",
            "prompt_sha256": "a" * 64,
            "dramatic_tags": ["relationship"],
            "energy": 0.5,
            "stem_profile": "pad",
            "keyscale": keyscale,
            "bpm": bpm,
            "edit_variant": edit_variant,
            "parent_asset_id": parent_asset_id,
            "transition_to_asset_id": transition_to_asset_id,
            "recipe": recipe,
        },
    )
    return approve_candidate(
        library,
        str(staged["asset_id"]),
        reviewer="dex",
        license_note="local personal use",
        instrumental_confirmed=True,
    )


def test_approved_library_renders_and_writes_checksum_bound_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    asset = _asset(library, _wav(tmp_path / "music.wav"))
    film = tmp_path / "film"
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    samples, selections = render_music_template_timeline(
        root=film,
        work=film / "work",
        timeline=[
            {
                "shot_id": "s1",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "mood": "rnb",
                "motif_id": "relationship",
                "dramatic_tags": ["relationship"],
                "energy": 0.5,
                "stem_profile": "pad",
                "transition": "cut",
                "seed": 3,
            }
        ],
        plan=None,
        music_license=None,
        seed=3,
        total_dur=1.0,
        approved_library=True,
        film_id="film",
        series_id="",
    )

    receipt = json.loads((film / "receipts/bgm-selection.json").read_text())
    assert len(samples) == 44100
    assert selections[0]["asset_id"] == asset["asset_id"]
    assert receipt["catalog_sha256"]


def test_approved_library_missing_mood_records_gap_and_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))
    with pytest.raises(RenderError, match="missing approved BGM"):
        render_music_template_timeline(
            root=tmp_path / "film",
            work=tmp_path / "film/work",
            timeline=[
                {
                    "shot_id": "s1",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "mood": "dark",
                    "motif_id": "threat",
                }
            ],
            plan=None,
            music_license=None,
            seed=1,
            total_dur=1.0,
            approved_library=True,
            film_id="film",
            series_id="",
        )
    assert (library / "gap-queue.jsonl").is_file()


def test_approved_library_blocks_raw_master_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    _asset(library, _wav(tmp_path / "long-master.wav", duration=10.0))
    film = tmp_path / "film"
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    with pytest.raises(RenderError, match="music edit plan requires offline approved assets"):
        render_music_template_timeline(
            root=film,
            work=film / "work",
            timeline=[
                {
                    "shot_id": "s1",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "mood": "rnb",
                    "motif_id": "relationship",
                    "energy": 0.5,
                    "stem_profile": "pad",
                    "transition": "cut",
                    "seed": 3,
                }
            ],
            plan=None,
            music_license=None,
            seed=3,
            total_dur=1.0,
            approved_library=True,
            film_id="film",
            series_id="",
        )

    plan = json.loads((film / "receipts/music-edit-plan.json").read_text())
    assert plan["ready_for_final"] is False
    assert plan["edits"][0]["strategy"] == "cover_cutdown"


def test_approved_library_blocks_subsecond_raw_master_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    _asset(library, _wav(tmp_path / "near-master.wav", duration=10.24))
    film = tmp_path / "film"
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    with pytest.raises(RenderError, match="music edit plan requires offline approved assets"):
        render_music_template_timeline(
            root=film,
            work=film / "work",
            timeline=[
                {
                    "shot_id": "s1",
                    "start_sec": 0.0,
                    "end_sec": 10.0,
                    "mood": "rnb",
                    "transition": "cut",
                }
            ],
            plan=None,
            music_license=None,
            seed=3,
            total_dur=10.0,
            approved_library=True,
            film_id="near-truncation-film",
            series_id="",
        )

    plan = json.loads((film / "receipts/music-edit-plan.json").read_text())
    assert plan["ready_for_final"] is False
    assert plan["edits"][0]["strategy"] == "repaint_outro"


def test_approved_library_renders_checksum_bound_transition_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    outgoing = _asset(
        library,
        _wav(tmp_path / "outgoing.wav", frequency=220),
        keyscale="A minor",
        bpm=72,
    )
    incoming = _asset(
        library,
        _wav(tmp_path / "incoming.wav", frequency=510),
        keyscale="F# major",
        bpm=110,
    )
    bridge = _asset(
        library,
        _wav(tmp_path / "bridge.wav", frequency=760),
        keyscale="F# major",
        bpm=110,
        edit_variant="bridge",
        parent_asset_id=str(outgoing["asset_id"]),
        transition_to_asset_id=str(incoming["asset_id"]),
    )
    film = tmp_path / "film"
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    samples, selections = render_music_template_timeline(
        root=film,
        work=film / "work",
        timeline=[
            {
                "shot_id": "s1",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "mood": "rnb",
                "preferred_asset_id": outgoing["asset_id"],
                "transition": "cut",
            },
            {
                "shot_id": "s2",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "mood": "rnb",
                "preferred_asset_id": incoming["asset_id"],
                "transition": "crossfade",
            },
        ],
        plan=None,
        music_license=None,
        seed=3,
        total_dur=2.0,
        approved_library=True,
        film_id="bridge-film",
        series_id="",
    )

    transition = selections[1]["transition_plan"]
    assert transition["mode"] == "approved_bridge"
    assert transition["bridge_asset_id"] == bridge["asset_id"]
    assert np.max(np.abs(samples)) > 0.1
    assert (film / "work/bgm_bridge_001.wav").is_file()


def test_final_success_commits_usage_once_and_updates_mix_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    asset = _asset(library, _wav(tmp_path / "music.wav"))
    film = tmp_path / "film"
    selection = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "film",
        "series_id": "",
        "catalog_revision": 2,
        "catalog_sha256": "c" * 64,
        "selections": [
            {
                "asset_id": asset["asset_id"],
                "shot_id": "s1",
                "sha256": asset["sha256"],
            }
        ],
    }
    (film / "receipts").mkdir(parents=True)
    (film / "audio").mkdir(parents=True)
    (film / "receipts/bgm-selection.json").write_text(json.dumps(selection))
    (film / "audio/mix_report.json").write_text(
        json.dumps(
            {
                "music_template": {
                    "source": "approved_library",
                    "mode": "approved_library",
                    "catalog_revision": 2,
                    "catalog_sha256": "c" * 64,
                    "selections": [
                        {
                            "asset_id": asset["asset_id"],
                            "shot_id": "s1",
                            "sha256": asset["sha256"],
                        }
                    ],
                }
            }
        )
    )
    final = _wav(film / "out/final.wav", frequency=440)
    checksum = hashlib.sha256(final.read_bytes()).hexdigest()
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    first = _commit_selected_bgm_usage(film, output=str(final), output_sha256=checksum)
    second = _commit_selected_bgm_usage(film, output=str(final), output_sha256=checksum)

    assert first and first["appended"] == 1
    assert second and second["appended"] == 0
    mix = json.loads((film / "audio/mix_report.json").read_text())
    assert mix["music_template"]["usage_commit"]["final_sha256"] == checksum


def test_stale_library_selection_is_not_committed_for_procedural_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    asset = _asset(library, _wav(tmp_path / "music.wav"))
    film = tmp_path / "film"
    (film / "receipts").mkdir(parents=True)
    (film / "audio").mkdir(parents=True)
    (film / "receipts/bgm-selection.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-selection-v1",
                "film_id": "old",
                "selections": [
                    {
                        "asset_id": asset["asset_id"],
                        "shot_id": "s1",
                        "sha256": asset["sha256"],
                    }
                ],
            }
        )
    )
    (film / "audio/mix_report.json").write_text(
        json.dumps({"music_template": {"source": "procedural", "mode": "auto"}})
    )
    final = _wav(film / "out/final.wav", frequency=440)
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    result = _commit_selected_bgm_usage(
        film,
        output=str(final),
        output_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
    )

    assert result is None
    assert not (library / "usage.jsonl").exists()


def test_init_ignores_corrupt_optional_bgm_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "catalog.json").write_text('{"schema":"broken","assets":{}}')
    film = tmp_path / "film"
    monkeypatch.setenv("AIFILM_BGM_LIBRARY_ROOT", str(library))

    result = cmd_init(
        Namespace(
            root=str(film),
            title="test",
            theme="test theme",
            aspect="9:16",
            force=False,
        )
    )

    assert result == 0
    spec = json.loads((film / "film-spec.json").read_text())
    assert "audio_policy" not in spec


def test_cli_exposes_approved_library_contract() -> None:
    parser = build_parser()
    args = parser.parse_args(["bgm-library", "status", "--library-root", "/tmp/library"])
    assert args.cmd == "bgm-library"
    canary = parser.parse_args(
        [
            "bgm-library",
            "canary",
            "--library-root",
            "/tmp/library",
            "--slot",
            "baseline-v1-rnb-pad",
            "--duration",
            "30",
            "--batch-size",
            "4",
        ]
    )
    assert canary.bgm_library_action == "canary"
    assert canary.duration == 30
    assert canary.batch_size == 4
    edit = parser.parse_args(
        [
            "bgm-library",
            "edit-pack",
            "--library-root",
            "/tmp/library",
            "--asset-id",
            "warm-1",
            "--duration",
            "20",
            "--variant",
            "exact",
            "--variant",
            "dialogue-safe",
        ]
    )
    assert edit.bgm_library_action == "edit-pack"
    assert edit.variant == ["exact", "dialogue-safe"]
    bridge = parser.parse_args(
        [
            "bgm-library",
            "bridge-pack",
            "--library-root",
            "/tmp/library",
            "--from-asset-id",
            "outgoing",
            "--to-asset-id",
            "incoming",
        ]
    )
    assert bridge.bgm_library_action == "bridge-pack"
    assert bridge.duration == 10.0
    edit_plan = parser.parse_args(["bgm-library", "edit-plan", "--root", "/tmp/film"])
    assert edit_plan.bgm_library_action == "edit-plan"
    final = parser.parse_args(
        ["final", "--root", "/tmp/film", "--music-template", "approved_library"]
    )
    assert final.music_template == "approved_library"


def test_canary_generates_one_bounded_pending_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates = [
        {
            "asset_id": f"a-{index}",
            "status": "pending_human_review",
            "sha256": f"{index + 1:064x}",
            "technical": {
                "ok": True,
                "duration_sec": 30.0,
                "fingerprint": [float(index), 0.5],
            },
        }
        for index in range(4)
    ]
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    emitted: list[dict[str, object]] = []
    args = Namespace(
        bgm_library_action="canary",
        library_root=str(tmp_path / "library"),
        slot="baseline-v1-rnb-pad",
        duration=30.0,
        batch_size=4,
        seed_base=5900,
    )

    with patch(
        "cli_bgm_library.generate_candidates",
        return_value={
            "ok": True,
            "recipe_id": "baseline-v1-rnb-pad",
            "node_job_id": "job",
            "candidates": candidates,
        },
    ) as generate:
        assert cmd_bgm_library(args, emit=emitted.append) == 0

    payload = generate.call_args.kwargs["recipe"]
    assert payload["duration"] == 30.0
    assert generate.call_args.kwargs["seeds"] == [5900, 5901, 5902, 5903]
    assert emitted[0]["ok"] is True
    assert emitted[0]["status"] == "pending_human_review"

    candidates[0]["technical"]["duration_sec"] = 20.0
    emitted.clear()
    with patch(
        "cli_bgm_library.generate_candidates",
        return_value={
            "ok": True,
            "recipe_id": "baseline-v1-rnb-pad",
            "node_job_id": "job",
            "candidates": candidates,
        },
    ):
        assert cmd_bgm_library(args, emit=emitted.append) == 2
    assert emitted[0]["ok"] is False
    assert emitted[0]["checks"]["duration_ok"] is False
    assert emitted[0]["checks"]["pending_only"] is True
