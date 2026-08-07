"""Music Director plan + apply (H3 native mute windows / peak) unit tests."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from music_director import (
    MusicDirectorError,
    apply_mute_windows_samples,
    apply_native_voice_plan,
    apply_peak_fix_samples,
    apply_plan,
    bgm_overlay_for_shot,
    build_review,
    draft_plan,
    merge_director_overrides,
    normalize_plan,
    resolve_directed_native_path,
    save_plan,
    set_shot_controls,
    apply_light_process_samples,
    load_audio_samples,
    discover_native_source,
    audit_native_peaks,
    apply_batch_edits,
    load_batch_edits,
    export_listen_checklist,
    apply_audit_peak_suggestions,
)


def _write_wav(path: Path, samples: np.ndarray, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def test_draft_plan_from_spec_native_defaults() -> None:
    spec = {
        "audio_policy": "prefer_native",
        "bgm_mood": "rnb",
        "shots": [
            {"id": "s01", "nar": "你好", "dialogue_audio_lane": "native", "dramatic_function": "hook"},
            {"id": "s02", "spoken_text": "错句", "dialogue_audio_lane": "native"},
            {"id": "s03", "dialogue_audio_lane": "silence"},
        ],
    }
    plan = draft_plan(spec=spec)
    assert plan["schema"].startswith("aifilm-music-director")
    assert plan["audio_policy"] == "prefer_native"
    assert plan["bgm"]["default_mood"] == "rnb"
    assert len(plan["bgm"]["shots"]) == 3
    voice = {r["shot_id"]: r for r in plan["native_voice"]["shots"]}
    assert voice["s01"]["lane"] == "native"
    assert voice["s03"]["mute_entire"] is True
    assert voice["s03"]["lane"] == "silence"


def test_normalize_rejects_inverted_mute_window() -> None:
    plan = draft_plan(
        spec={"shots": [{"id": "s1", "nar": "a", "dialogue_audio_lane": "native"}]}
    )
    plan["native_voice"]["shots"][0]["mute_windows"] = [
        {"start_sec": 2.0, "end_sec": 1.0, "reason": "bad"}
    ]
    with pytest.raises(MusicDirectorError, match="mute window invalid"):
        normalize_plan(plan)


def test_mute_entire_forces_silence_lane() -> None:
    plan = draft_plan(
        spec={"shots": [{"id": "s1", "nar": "a", "dialogue_audio_lane": "native"}]}
    )
    plan["native_voice"]["shots"][0]["mute_entire"] = True
    plan["native_voice"]["shots"][0]["lane"] = "native"
    out = normalize_plan(plan)
    assert out["native_voice"]["shots"][0]["lane"] == "silence"
    assert out["native_voice"]["shots"][0]["mute_entire"] is True


def test_merge_director_overrides_wins_on_mute_windows() -> None:
    base = draft_plan(
        spec={"shots": [{"id": "s1", "nar": "a", "dialogue_audio_lane": "native"}]}
    )
    merged = merge_director_overrides(
        base,
        {
            "source": "director",
            "native_voice": {
                "shots": [
                    {
                        "shot_id": "s1",
                        "mute_windows": [
                            {
                                "start_sec": 0.5,
                                "end_sec": 1.0,
                                "reason": "wrong_line",
                                "source": "director",
                            }
                        ],
                    }
                ]
            },
        },
    )
    wins = merged["native_voice"]["shots"][0]["mute_windows"]
    assert len(wins) == 1
    assert wins[0]["start_sec"] == 0.5
    assert wins[0]["reason"] == "wrong_line"
    assert merged["source"] == "director"


def test_apply_mute_windows_zeros_mid_band() -> None:
    sr = 1000
    samples = np.ones(sr, dtype=np.float32) * 0.5
    out = apply_mute_windows_samples(
        samples,
        sr,
        [{"start_sec": 0.2, "end_sec": 0.5}],
    )
    assert float(np.max(np.abs(out[0:200]))) > 0.4
    assert float(np.max(np.abs(out[200:500]))) < 1e-6
    assert float(np.max(np.abs(out[500:]))) > 0.4


def test_apply_peak_fix_reduces_hot_peak() -> None:
    hot = np.array([0.0, 0.99, -0.99, 0.5], dtype=np.float32)
    fixed, meta = apply_peak_fix_samples(
        hot, true_peak_dbtp=-1.5, gain=1.0, peak_fix="auto", limiter=0.95
    )
    assert meta["peak_dbfs_after"] <= -1.4
    assert float(np.max(np.abs(fixed))) <= 10 ** (-1.5 / 20.0) + 1e-5


def test_apply_native_writes_directed_stem(tmp_path: Path) -> None:
    root = tmp_path / "film"
    native = root / "audio" / "native"
    native.mkdir(parents=True)
    sr = 8000
    # 1s tone with mid spike region
    t = np.linspace(0, 1, sr, endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    samples[int(0.4 * sr) : int(0.6 * sr)] = 0.99  # hot wrong-line zone
    _write_wav(native / "s1.wav", samples, sr=sr)

    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_policy": "prefer_native",
                "shots": [{"id": "s1", "nar": "你好", "dialogue_audio_lane": "native"}],
            }
        ),
        encoding="utf-8",
    )
    plan = draft_plan(root=root)
    plan = merge_director_overrides(
        plan,
        {
            "native_voice": {
                "shots": [
                    {
                        "shot_id": "s1",
                        "mute_windows": [
                            {
                                "start_sec": 0.4,
                                "end_sec": 0.6,
                                "reason": "wrong_line",
                                "source": "director",
                            }
                        ],
                        "peak_fix": "auto",
                    }
                ]
            }
        },
    )
    save_plan(root, plan)
    receipt = apply_native_voice_plan(root, plan)
    assert receipt["ok"] is True
    assert receipt["mute_window_count"] == 1
    dest = root / "audio" / "native_directed" / "s1.wav"
    assert dest.is_file()

    with wave.open(str(dest), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        out = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    mid = out[int(0.4 * sr) : int(0.6 * sr)]
    assert float(np.max(np.abs(mid))) < 1e-3

    directed = resolve_directed_native_path(root, "s1", source_path=native / "s1.wav")
    assert directed is not None
    assert directed == dest

    review = build_review(root, plan)
    assert review["picture_timing_changed"] is False
    assert any(m.get("kind") == "window" for m in review["native_voice"]["mute_actions"])


def test_bgm_overlay_and_full_apply(tmp_path: Path) -> None:
    root = tmp_path / "film"
    (root / "audio" / "native").mkdir(parents=True)
    _write_wav(root / "audio" / "native" / "a.wav", np.zeros(1000, dtype=np.float32) + 0.1)
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_policy": "prefer_native",
                "shots": [
                    {
                        "id": "a",
                        "nar": "hi",
                        "dialogue_audio_lane": "native",
                        "music_cue": {"mood": "rnb", "energy": 0.2},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = draft_plan(root=root)
    plan["bgm"]["shots"][0]["duck_db"] = -12.0
    plan["bgm"]["shots"][0]["energy"] = 0.3
    result = apply_plan(root, plan, patch_spec=True)
    assert result["ok"] is True
    row = bgm_overlay_for_shot(plan, "a")
    assert row is not None
    assert row["duck_db"] == -12.0
    spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
    assert spec["shots"][0]["music_cue"]["duck_db"] == -12.0


def test_set_shot_controls_adds_mute_window_and_duck() -> None:
    plan = draft_plan(
        spec={"shots": [{"id": "s1", "nar": "a", "dialogue_audio_lane": "native"}]}
    )
    plan = set_shot_controls(
        plan,
        "s1",
        mute_window=(1.0, 1.5),
        mute_reason="wrong_line",
        duck_db=-9.0,
    )
    voice = plan["native_voice"]["shots"][0]
    assert voice["mute_windows"][0]["start_sec"] == 1.0
    assert voice["mute_windows"][0]["reason"] == "wrong_line"
    bgm = plan["bgm"]["shots"][0]
    assert bgm["duck_db"] == -9.0


def test_discover_prefers_clips_media(tmp_path: Path) -> None:
    root = tmp_path / "film"
    clips = root / "clips"
    clips.mkdir(parents=True)
    # tiny silent wav as "clip" media
    import wave
    import numpy as np

    wav = clips / "s9.wav"
    pcm = (np.zeros(800, dtype=np.float32) * 0).astype(np.int16)
    # write via wave
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(pcm.tobytes())
    hit = discover_native_source(root, "s9")
    assert hit == wav


def test_light_process_removes_dc_offset() -> None:
    import numpy as np

    sr = 1000
    samples = np.ones(sr, dtype=np.float32) * 0.2  # DC
    out = apply_light_process_samples(samples, sr)
    assert abs(float(np.mean(out))) < 0.05


def test_load_audio_samples_wav(tmp_path: Path) -> None:
    import numpy as np
    import wave

    path = tmp_path / "t.wav"
    sr = 8000
    pcm = (np.linspace(-0.5, 0.5, sr) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    samples, out_sr, meta = load_audio_samples(path)
    assert out_sr == sr
    assert meta["decode"] == "wav"
    assert len(samples) == sr


def test_audit_marks_hot_peak(tmp_path: Path) -> None:
    import json
    import numpy as np
    import wave

    root = tmp_path / "film"
    native = root / "audio" / "native"
    native.mkdir(parents=True)
    sr = 4000
    hot = (np.ones(sr, dtype=np.float32) * 0.99)
    pcm = (hot * 32767).astype(np.int16)
    with wave.open(str(native / "h1.wav"), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_policy": "prefer_native",
                "shots": [{"id": "h1", "nar": "hi", "dialogue_audio_lane": "native"}],
            }
        ),
        encoding="utf-8",
    )
    plan = draft_plan(root=root)
    rep = audit_native_peaks(root, plan)
    assert "h1" in rep["hot_shot_ids"]


def test_batch_edits_and_jsonl(tmp_path: Path) -> None:
    plan = draft_plan(
        spec={
            "shots": [
                {"id": "a", "nar": "1", "dialogue_audio_lane": "native"},
                {"id": "b", "nar": "2", "dialogue_audio_lane": "native"},
            ]
        }
    )
    plan = apply_batch_edits(
        plan,
        [
            {"shot_id": "a", "mute_window": [0.1, 0.3], "reason": "wrong_line", "duck_db": -8},
            {"shot_id": "b", "mute_entire": True},
        ],
    )
    by = {r["shot_id"]: r for r in plan["native_voice"]["shots"]}
    assert by["a"]["mute_windows"][0]["end_sec"] == 0.3
    assert by["b"]["mute_entire"] is True
    assert by["b"]["lane"] == "silence"
    bgm = {r["shot_id"]: r for r in plan["bgm"]["shots"]}
    assert bgm["a"]["duck_db"] == -8.0

    jl = tmp_path / "e.jsonl"
    jl.write_text(
        '{"shot_id":"a","mute_window":"0.5:0.8","reason":"x"}\n',
        encoding="utf-8",
    )
    edits = load_batch_edits(jl)
    plan2 = apply_batch_edits(plan, edits)
    wins = [w for w in plan2["native_voice"]["shots"] if w["shot_id"] == "a"][0]["mute_windows"]
    assert any(abs(w["start_sec"] - 0.5) < 1e-6 for w in wins)


def test_export_listen_checklist(tmp_path: Path) -> None:
    import json
    import numpy as np
    import wave

    root = tmp_path / "film"
    native = root / "audio" / "native"
    native.mkdir(parents=True)
    sr = 4000
    hot = (np.ones(sr, dtype=np.float32) * 0.99)
    pcm = (hot * 32767).astype(np.int16)
    with wave.open(str(native / "c1.wav"), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_policy": "prefer_native",
                "shots": [{"id": "c1", "nar": "hi", "dialogue_audio_lane": "native"}],
            }
        ),
        encoding="utf-8",
    )
    plan = draft_plan(root=root)
    plan = set_shot_controls(plan, "c1", mute_window=(0.1, 0.2), duck_db=-6)
    save_plan(root, plan)
    rep = export_listen_checklist(root, plan, write=True)
    assert rep["counts"]["must_listen"] >= 1
    assert (root / "receipts" / "music-director-checklist.md").is_file()
    assert (root / "receipts" / "music-director-checklist.json").is_file()
    assert "c1" in rep["markdown"]


def test_apply_audit_peak_suggestions() -> None:
    plan = draft_plan(
        spec={"shots": [{"id": "z", "nar": "n", "dialogue_audio_lane": "native"}]}
    )
    # force off then suggestions set auto
    plan = set_shot_controls(plan, "z", peak_fix="off")
    audit = {"hot_shot_ids": ["z"]}
    plan2 = apply_audit_peak_suggestions(plan, audit)
    row = plan2["native_voice"]["shots"][0]
    assert row["peak_fix"] == "auto"
