from __future__ import annotations

import hashlib
import json
import math
import wave
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest
from aifilm_grok import _commit_selected_bgm_usage, build_parser, cmd_init
from bgm_library import approve_candidate, stage_candidate
from render_final import RenderError, render_music_template_timeline


def _wav(path: Path, frequency: float = 220.0) -> Path:
    rate = 44100
    t = np.arange(rate, dtype=np.float64)
    signal = np.sin(2.0 * math.pi * frequency * t / rate) * 0.25
    stereo = np.column_stack((signal, signal))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((stereo * 32767).astype("<i2").tobytes())
    return path


def _asset(library: Path, source: Path) -> dict[str, object]:
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
            "recipe": {
                "mood": "rnb",
                "dramatic_tags": ["relationship"],
                "energy": 0.5,
                "stem_profile": "pad",
            },
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
    final = parser.parse_args(
        ["final", "--root", "/tmp/film", "--music-template", "approved_library"]
    )
    assert final.music_template == "approved_library"
