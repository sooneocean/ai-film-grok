from __future__ import annotations

import hashlib
import json
import math
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from bgm_library import (
    BGMLibraryError,
    approve_candidate,
    audit_library,
    baseline_recipes,
    commit_usage,
    generate_candidates,
    library_status,
    reject_candidate,
    select_timeline,
    stage_candidate,
    write_review_pack,
)


def _wav(path: Path, *, frequency: float, gain: float = 0.35, duration: float = 1.0) -> Path:
    sample_rate = 44100
    samples = np.arange(int(sample_rate * duration), dtype=np.float64)
    signal = np.sin(2.0 * math.pi * frequency * samples / sample_rate) * gain
    stereo = np.column_stack((signal, signal))
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def _pcm_variant(source: Path, output: Path, *, crop_frames: int = 0, quantize: int = 1) -> Path:
    with wave.open(str(source), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        pcm = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").reshape(
            -1, channels
        )
    pcm = pcm[crop_frames:]
    if quantize > 1:
        pcm = ((pcm.astype(np.int32) // quantize) * quantize).astype("<i2")
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.astype("<i2").tobytes())
    return output


def _metadata(
    *,
    mood: str = "rnb",
    seed: int = 1,
    energy: float = 0.5,
    stem_profile: str = "pad",
    motif_family: str = "",
    parent_asset_id: str | None = None,
    keyscale: str = "A minor",
    bpm: int = 72,
) -> dict[str, object]:
    recipe = {
        "mood": mood,
        "dramatic_tags": ["relationship", "intimacy"],
        "energy": energy,
        "stem_profile": stem_profile,
        "bpm": bpm,
        "keyscale": keyscale,
        "timesignature": "4/4",
        "motif_family": motif_family,
    }
    return {
        **recipe,
        "seed": seed,
        "model": "ACE-Step-1.5",
        "checkpoint_fingerprint": "checkpoint-test",
        "prompt_sha256": hashlib.sha256(json.dumps(recipe).encode()).hexdigest(),
        "parent_asset_id": parent_asset_id,
        "recipe": recipe,
    }


def _approved(
    library: Path,
    source: Path,
    *,
    mood: str,
    seed: int,
    energy: float = 0.5,
    stem_profile: str = "pad",
    motif_family: str = "",
    parent_asset_id: str | None = None,
    keyscale: str = "A minor",
    bpm: int = 72,
) -> dict[str, object]:
    staged = stage_candidate(
        library,
        source,
        _metadata(
            mood=mood,
            seed=seed,
            energy=energy,
            stem_profile=stem_profile,
            motif_family=motif_family,
            parent_asset_id=parent_asset_id,
            keyscale=keyscale,
            bpm=bpm,
        ),
    )
    return approve_candidate(
        library,
        str(staged["asset_id"]),
        reviewer="dex",
        license_note="ACE-Step local generation; personal use",
        instrumental_confirmed=True,
    )


def test_catalog_is_atomic_and_approval_keeps_reproducible_metadata(tmp_path: Path) -> None:
    library = tmp_path / "library"
    source = _wav(tmp_path / "candidate.wav", frequency=220)
    staged = stage_candidate(library, source, _metadata())

    assert staged["status"] == "pending_human_review"
    assert not (library / "catalog.json").read_text().count("private prompt")

    approved = approve_candidate(
        library,
        str(staged["asset_id"]),
        reviewer="dex",
        license_note="ACE-Step local generation; personal use",
        instrumental_confirmed=True,
    )
    catalog = json.loads((library / "catalog.json").read_text())
    record = catalog["assets"][approved["asset_id"]]

    assert approved["status"] == "approved"
    assert approved["instrumental"] is True
    assert record["technical"]["ok"]
    assert record["human_review"]["instrumental_confirmed"]
    assert record["recipe"]["mood"] == "rnb"
    assert record["path"].startswith("approved/")
    assert (library / record["path"]).is_file()


def test_empty_library_status_hash_is_stable(tmp_path: Path) -> None:
    library = tmp_path / "library"

    first = library_status(library)
    second = library_status(library)

    assert first["catalog_sha256"] == second["catalog_sha256"]
    assert first["ready_for_default"] is False


def test_candidate_source_symlink_is_rejected(tmp_path: Path) -> None:
    source = _wav(tmp_path / "source.wav", frequency=220)
    link = tmp_path / "linked.wav"
    link.symlink_to(source)
    with pytest.raises(BGMLibraryError, match="symlinked"):
        stage_candidate(tmp_path / "library", link, _metadata())


def test_approval_rejects_exact_and_perceptual_duplicates(tmp_path: Path) -> None:
    library = tmp_path / "library"
    original = _approved(
        library,
        _wav(tmp_path / "one.wav", frequency=220, gain=0.2),
        mood="rnb",
        seed=1,
    )

    exact = stage_candidate(library, library / str(original["path"]), _metadata(seed=2))
    with pytest.raises(BGMLibraryError, match="exact duplicate"):
        approve_candidate(
            library,
            str(exact["asset_id"]),
            reviewer="dex",
            license_note="local",
            instrumental_confirmed=True,
        )

    louder = stage_candidate(
        library,
        _wav(tmp_path / "louder.wav", frequency=220, gain=0.7),
        _metadata(seed=3),
    )
    with pytest.raises(BGMLibraryError, match="near duplicate"):
        approve_candidate(
            library,
            str(louder["asset_id"]),
            reviewer="dex",
            license_note="local",
            instrumental_confirmed=True,
        )


def test_approval_rejects_cropped_and_requantized_near_duplicates(tmp_path: Path) -> None:
    library = tmp_path / "library"
    original_path = _wav(tmp_path / "master.wav", frequency=293, duration=3.0)
    _approved(library, original_path, mood="rnb", seed=1)
    variants = (
        _pcm_variant(
            original_path,
            tmp_path / "cropped.wav",
            crop_frames=44100 // 4,
        ),
        _pcm_variant(
            original_path,
            tmp_path / "requantized.wav",
            quantize=256,
        ),
    )

    for seed, variant in enumerate(variants, start=2):
        staged = stage_candidate(library, variant, _metadata(seed=seed))
        with pytest.raises(BGMLibraryError, match="near duplicate"):
            approve_candidate(
                library,
                str(staged["asset_id"]),
                reviewer="dex",
                license_note="local",
                instrumental_confirmed=True,
            )


def test_same_motif_lineage_may_share_cluster_but_not_play_adjacent(tmp_path: Path) -> None:
    library = tmp_path / "library"
    parent = _approved(
        library,
        _wav(tmp_path / "parent.wav", frequency=220, gain=0.2),
        mood="warm",
        seed=1,
        motif_family="hero",
    )
    child = _approved(
        library,
        _wav(tmp_path / "child.wav", frequency=220, gain=0.7),
        mood="warm",
        seed=2,
        motif_family="hero",
        parent_asset_id=str(parent["asset_id"]),
    )

    assert child["similarity_cluster"] == parent["similarity_cluster"]
    with pytest.raises(BGMLibraryError, match="no eligible approved BGM"):
        select_timeline(
            library,
            film_id="film-one",
            series_id="series-a",
            timeline=[
                {
                    "shot_id": "s1",
                    "mood": "warm",
                    "motif_id": "hero",
                    "energy": 0.2,
                    "stem_profile": "pad",
                },
                {
                    "shot_id": "s2",
                    "mood": "warm",
                    "motif_id": "hero",
                    "energy": 0.8,
                    "stem_profile": "full",
                },
            ],
            require_complete=True,
        )


def test_generic_master_can_be_explicit_parent_of_series_motif(tmp_path: Path) -> None:
    library = tmp_path / "library"
    parent = _approved(
        library,
        _wav(tmp_path / "master.wav", frequency=260, gain=0.2),
        mood="warm",
        seed=1,
    )
    metadata = _metadata(
        mood="warm",
        seed=2,
        motif_family="protagonist",
        parent_asset_id=str(parent["asset_id"]),
    )
    metadata["series_id"] = "series-a"
    staged = stage_candidate(
        library,
        _wav(tmp_path / "variation.wav", frequency=260, gain=0.4),
        metadata,
    )
    child = approve_candidate(
        library,
        str(staged["asset_id"]),
        reviewer="dex",
        license_note="ACE-Step cover of approved master",
        instrumental_confirmed=True,
    )

    assert child["parent_asset_id"] == parent["asset_id"]
    assert child["similarity_cluster"] == parent["similarity_cluster"]


def test_selector_avoids_asset_reuse_and_recent_films(tmp_path: Path) -> None:
    library = tmp_path / "library"
    assets = [
        _approved(
            library,
            _wav(tmp_path / f"{index}.wav", frequency=180 + index * 47),
            mood="dark",
            seed=index,
            energy=index / 10,
            stem_profile="pulse" if index % 2 else "pad",
        )
        for index in range(1, 7)
    ]
    old_receipt = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "previous-film",
        "selections": [
            {
                "asset_id": assets[0]["asset_id"],
                "shot_id": "old",
                "sha256": assets[0]["sha256"],
            }
        ],
    }
    commit_usage(library, old_receipt, final_sha256="a" * 64)

    receipt = select_timeline(
        library,
        film_id="new-film",
        series_id="",
        timeline=[
            {
                "shot_id": f"s{index}",
                "mood": "dark",
                "motif_id": "threat",
                "dramatic_tags": ["crisis"],
                "energy": index / 10,
                "stem_profile": "pulse",
            }
            for index in range(1, 5)
        ],
        require_complete=True,
    )
    selected = [item["asset_id"] for item in receipt["selections"]]

    assert len(selected) == len(set(selected)) == 4
    assert assets[0]["asset_id"] not in selected
    assert all(item["selection_reason"] for item in receipt["selections"])


def test_ten_cues_have_no_asset_or_adjacent_cluster_reuse(tmp_path: Path) -> None:
    library = tmp_path / "library"
    frequencies = (110, 160, 230, 340, 500, 730, 1060, 1540, 2240, 3260)
    for index, frequency in enumerate(frequencies):
        _approved(
            library,
            _wav(tmp_path / f"ten-{index}.wav", frequency=frequency),
            mood="playful",
            seed=index + 1,
            energy=index / 10,
            stem_profile=("pad", "thin", "pulse", "full")[index % 4],
        )

    receipt = select_timeline(
        library,
        film_id="ten-cue-film",
        timeline=[
            {
                "shot_id": f"s{index:02d}",
                "mood": "playful",
                "energy": index / 10,
                "stem_profile": ("pad", "thin", "pulse", "full")[index % 4],
            }
            for index in range(10)
        ],
    )

    asset_ids = [item["asset_id"] for item in receipt["selections"]]
    clusters = [item["similarity_cluster"] for item in receipt["selections"]]
    assert len(asset_ids) == len(set(asset_ids)) == 10
    assert all(left != right for left, right in zip(clusters, clusters[1:], strict=False))


def test_six_films_rotate_across_recent_assets(tmp_path: Path) -> None:
    library = tmp_path / "library"
    for index in range(6):
        _approved(
            library,
            _wav(tmp_path / f"film-{index}.wav", frequency=190 + index * 67),
            mood="warm",
            seed=index + 1,
        )

    chosen: list[str] = []
    for index in range(6):
        receipt = select_timeline(
            library,
            film_id=f"film-{index}",
            timeline=[{"shot_id": "s1", "mood": "warm"}],
        )
        chosen.append(str(receipt["selections"][0]["asset_id"]))
        commit_usage(library, receipt, final_sha256=f"{index + 1:064x}")

    assert len(chosen) == len(set(chosen)) == 6


def test_selection_fails_closed_when_approved_asset_is_replaced(tmp_path: Path) -> None:
    library = tmp_path / "library"
    asset = _approved(
        library,
        _wav(tmp_path / "approved.wav", frequency=610),
        mood="rnb",
        seed=1,
    )
    approved_path = library / str(asset["path"])
    approved_path.write_bytes(_wav(tmp_path / "replacement.wav", frequency=330).read_bytes())

    with pytest.raises(BGMLibraryError, match="integrity"):
        select_timeline(
            library,
            film_id="film",
            timeline=[{"shot_id": "s1", "mood": "rnb"}],
        )


def test_usage_commit_is_idempotent_and_updates_status(tmp_path: Path) -> None:
    library = tmp_path / "library"
    asset = _approved(
        library,
        _wav(tmp_path / "asset.wav", frequency=330),
        mood="playful",
        seed=1,
    )
    receipt = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "film",
        "selections": [
            {
                "asset_id": asset["asset_id"],
                "shot_id": "s1",
                "sha256": asset["sha256"],
            }
        ],
    }

    first = commit_usage(library, receipt, final_sha256="b" * 64)
    second = commit_usage(library, receipt, final_sha256="b" * 64)
    lines = (library / "usage.jsonl").read_text().splitlines()

    assert first["appended"] == 1
    assert second["appended"] == 0
    assert len(lines) == 1
    status = library_status(library)
    assert status["assets"][asset["asset_id"]]["use_count"] == 1


def test_review_pack_and_rejection_are_auditable(tmp_path: Path) -> None:
    library = tmp_path / "library"
    staged = stage_candidate(
        library,
        _wav(tmp_path / "review.wav", frequency=440),
        _metadata(mood="sensual"),
    )
    review = write_review_pack(library)
    html = Path(review["path"]).read_text()

    assert str(staged["asset_id"]) in html
    assert "<audio controls" in html
    assert "标准化配方" in html
    assert "duration" in html
    assert "loop seam" in html
    assert "dialogue band" in html
    rejected = reject_candidate(library, str(staged["asset_id"]), reviewer="dex", reason="vocal")
    assert rejected["status"] == "rejected"
    assert audit_library(library)["ok"]


def test_edit_candidate_must_match_requested_duration(tmp_path: Path) -> None:
    metadata = _metadata(mood="warm")
    metadata["duration"] = 20.0
    metadata["edit_variant"] = "exact"
    metadata["recipe"] = {
        **dict(metadata["recipe"]),
        "duration": 20.0,
        "edit_variant": "exact",
    }

    with pytest.raises(BGMLibraryError, match="target_duration_mismatch"):
        stage_candidate(
            tmp_path / "library",
            _wav(tmp_path / "too-short.wav", frequency=440, duration=1.0),
            metadata,
        )


def test_baseline_pack_has_five_moods_and_twenty_slots() -> None:
    recipes = baseline_recipes()
    assert len(recipes) == 20
    assert {item["mood"] for item in recipes} == {
        "rnb",
        "sensual",
        "dark",
        "warm",
        "playful",
    }


def test_generate_candidates_uses_batch_node_and_never_stores_prompt(tmp_path: Path) -> None:
    library = tmp_path / "library"
    rendered = []
    for index, frequency in enumerate((220, 330, 440, 550)):
        rendered.append(
            {
                "path": str(_wav(tmp_path / f"batch-{index}.wav", frequency=frequency)),
                "sha256": "",
                "seed": 10 + index,
                "index": index,
            }
        )
        rendered[-1]["sha256"] = hashlib.sha256(
            Path(str(rendered[-1]["path"])).read_bytes()
        ).hexdigest()
    node_receipt = {
        "job_id": "job-batch",
        "model": "ACE-Step-1.5",
        "checkpoint_fingerprint": "checkpoint",
        "artifacts": rendered,
    }
    recipe = baseline_recipes()[0]

    with patch("bgm_library.render_batch", return_value=node_receipt) as render:
        result = generate_candidates(
            library,
            base_url="http://node",
            token="x" * 32,
            recipe=recipe,
            batch_size=4,
            seeds=[10, 11, 12, 13],
        )

    assert len(result["candidates"]) == 4
    assert render.call_args.kwargs["payload"]["batch_size"] == 4
    catalog_text = (library / "catalog.json").read_text()
    assert recipe["prompt"] not in catalog_text
    assert "prompt_sha256" in catalog_text


def test_generate_candidates_leaves_no_partial_batch_on_bad_wav(tmp_path: Path) -> None:
    library = tmp_path / "library"
    good = _wav(tmp_path / "good.wav", frequency=220)
    clipped = _wav(tmp_path / "clipped.wav", frequency=330, gain=1.0)
    node_receipt = {
        "job_id": "job-batch",
        "model": "ACE-Step-1.5",
        "checkpoint_fingerprint": "checkpoint",
        "artifacts": [
            {"path": str(good), "sha256": hashlib.sha256(good.read_bytes()).hexdigest(), "seed": 1},
            {
                "path": str(clipped),
                "sha256": hashlib.sha256(clipped.read_bytes()).hexdigest(),
                "seed": 2,
            },
        ],
    }
    with (
        patch("bgm_library.render_batch", return_value=node_receipt),
        pytest.raises(BGMLibraryError, match="technical"),
    ):
        generate_candidates(
            library,
            base_url="http://node",
            token="x" * 32,
            recipe=baseline_recipes()[0],
            batch_size=2,
            seeds=[1, 2],
        )

    assert library_status(library)["counts"]["pending_human_review"] == 0


def test_generate_candidates_rejects_duplicate_batch_before_catalog(tmp_path: Path) -> None:
    library = tmp_path / "library"
    duplicate = _wav(tmp_path / "duplicate.wav", frequency=220)
    checksum = hashlib.sha256(duplicate.read_bytes()).hexdigest()
    node_receipt = {
        "job_id": "job-duplicate",
        "model": "ACE-Step-1.5",
        "checkpoint_fingerprint": "checkpoint",
        "artifacts": [
            {"path": str(duplicate), "sha256": checksum, "seed": 1},
            {"path": str(duplicate), "sha256": checksum, "seed": 2},
        ],
    }

    with (
        patch("bgm_library.render_batch", return_value=node_receipt),
        pytest.raises(BGMLibraryError, match="unique"),
    ):
        generate_candidates(
            library,
            base_url="http://node",
            token="x" * 32,
            recipe=baseline_recipes()[0],
            batch_size=2,
            seeds=[1, 2],
        )

    assert library_status(library)["counts"]["pending_human_review"] == 0


def test_recent_window_uses_thirty_days_when_usage_is_loaded(tmp_path: Path) -> None:
    library = tmp_path / "library"
    asset = _approved(
        library,
        _wav(tmp_path / "old.wav", frequency=610),
        mood="rnb",
        seed=1,
    )
    event = {
        "event_id": "old",
        "film_id": "old-film",
        "asset_id": asset["asset_id"],
        "shot_id": "old",
        "final_sha256": "f" * 64,
        "used_at": (datetime.now(UTC) - timedelta(days=31)).isoformat(),
    }
    (library / "usage.jsonl").write_text(json.dumps(event) + "\n")
    receipt = select_timeline(
        library,
        film_id="new-film",
        series_id="",
        timeline=[
            {
                "shot_id": "s1",
                "mood": "rnb",
                "motif_id": "relationship",
                "energy": 0.5,
                "stem_profile": "pad",
            }
        ],
        require_complete=True,
    )
    assert receipt["selections"][0]["asset_id"] == asset["asset_id"]


def test_selector_prefers_harmonic_continuity_and_writes_transition_plan(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    first = _approved(
        library,
        _wav(tmp_path / "first.wav", frequency=220),
        mood="warm",
        seed=1,
        keyscale="A minor",
        bpm=72,
    )
    compatible = _approved(
        library,
        _wav(tmp_path / "compatible.wav", frequency=330),
        mood="warm",
        seed=2,
        keyscale="C Major",
        bpm=74,
    )
    _approved(
        library,
        _wav(tmp_path / "distant.wav", frequency=510),
        mood="warm",
        seed=3,
        keyscale="F# Major",
        bpm=128,
    )

    receipt = select_timeline(
        library,
        film_id="harmonic-film",
        timeline=[
            {
                "shot_id": "s1",
                "mood": "warm",
                "energy": 0.5,
                "stem_profile": "pad",
                "preferred_asset_id": first["asset_id"],
            },
            {
                "shot_id": "s2",
                "mood": "warm",
                "energy": 0.5,
                "stem_profile": "pad",
                "transition": "crossfade",
            },
        ],
    )

    assert receipt["selections"][0]["asset_id"] == first["asset_id"]
    assert receipt["selections"][1]["asset_id"] == compatible["asset_id"]
    assert receipt["selections"][1]["transition_plan"]["mode"] == "beat_crossfade"
    assert "harmonic_continuity" in receipt["selections"][1]["selection_reason"]


def test_selector_uses_approved_bridge_for_incompatible_authored_pair(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    outgoing = _approved(
        library,
        _wav(tmp_path / "outgoing.wav", frequency=220),
        mood="warm",
        seed=1,
        keyscale="A minor",
        bpm=72,
    )
    incoming = _approved(
        library,
        _wav(tmp_path / "incoming.wav", frequency=510),
        mood="warm",
        seed=2,
        keyscale="F# Major",
        bpm=110,
    )
    metadata = _metadata(mood="warm", seed=3, keyscale="F# Major", bpm=110)
    metadata["edit_variant"] = "bridge"
    metadata["parent_asset_id"] = outgoing["asset_id"]
    metadata["transition_to_asset_id"] = incoming["asset_id"]
    metadata["recipe"] = {
        **dict(metadata["recipe"]),
        "edit_variant": "bridge",
        "parent_asset_id": outgoing["asset_id"],
        "transition_to_asset_id": incoming["asset_id"],
    }
    bridge_staged = stage_candidate(
        library,
        _wav(tmp_path / "bridge.wav", frequency=760),
        metadata,
    )
    bridge = approve_candidate(
        library,
        str(bridge_staged["asset_id"]),
        reviewer="dex",
        license_note="approved ACE transition bridge",
        instrumental_confirmed=True,
    )

    receipt = select_timeline(
        library,
        film_id="bridge-film",
        timeline=[
            {
                "shot_id": "s1",
                "mood": "warm",
                "preferred_asset_id": outgoing["asset_id"],
            },
            {
                "shot_id": "s2",
                "mood": "warm",
                "preferred_asset_id": incoming["asset_id"],
                "transition": "crossfade",
            },
        ],
    )

    assert [item["asset_id"] for item in receipt["selections"]] == [
        outgoing["asset_id"],
        incoming["asset_id"],
    ]
    transition = receipt["selections"][1]["transition_plan"]
    assert transition["mode"] == "approved_bridge"
    assert transition["bridge_asset_id"] == bridge["asset_id"]
    assert transition["generation_required"] is False


def test_usage_ledger_includes_approved_transition_bridge(tmp_path: Path) -> None:
    library = tmp_path / "library"
    outgoing = _approved(
        library,
        _wav(tmp_path / "outgoing.wav", frequency=220),
        mood="warm",
        seed=1,
    )
    incoming = _approved(
        library,
        _wav(tmp_path / "incoming.wav", frequency=510),
        mood="warm",
        seed=2,
    )
    metadata = _metadata(mood="warm", seed=3)
    metadata.update(
        {
            "edit_variant": "bridge",
            "parent_asset_id": outgoing["asset_id"],
            "transition_to_asset_id": incoming["asset_id"],
        }
    )
    metadata["recipe"] = {
        **dict(metadata["recipe"]),
        "edit_variant": "bridge",
        "parent_asset_id": outgoing["asset_id"],
        "transition_to_asset_id": incoming["asset_id"],
    }
    staged = stage_candidate(
        library,
        _wav(tmp_path / "bridge.wav", frequency=760),
        metadata,
    )
    bridge = approve_candidate(
        library,
        str(staged["asset_id"]),
        reviewer="dex",
        license_note="approved ACE transition bridge",
        instrumental_confirmed=True,
    )
    receipt = {
        "schema": "aifilm-bgm-selection-v1",
        "film_id": "film",
        "series_id": "",
        "selections": [
            {
                "shot_id": "s2",
                "asset_id": incoming["asset_id"],
                "sha256": incoming["sha256"],
                "transition_plan": {
                    "mode": "approved_bridge",
                    "bridge_asset_id": bridge["asset_id"],
                    "bridge_sha256": bridge["sha256"],
                },
            }
        ],
    }

    result = commit_usage(library, receipt, final_sha256="f" * 64)
    events = [
        json.loads(line)
        for line in (library / "usage.jsonl").read_text().splitlines()
        if line.strip()
    ]

    assert result["appended"] == 2
    assert {event["usage_role"] for event in events} == {"cue", "transition_bridge"}
    assert events[1]["shot_id"] == "s2:transition"
