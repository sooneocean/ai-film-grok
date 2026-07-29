from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_plan import build_audio_plan
from audio_timeline import (
    AudioTimelineError,
    build_mix_execution_plan,
    caption_bindings,
    compile_timeline,
    rebase_to_rendered_shots,
    validate_timeline,
)
from performance_candidates import sign_receipt
from util import write_json
from voice_cast_profiles import VoiceCastError, assign_profiles, validate_event_language


def _spec(cues, *, mode="drama_radio"):
    return {"audio_style": mode, "shots": [{"id": "s1", "duration_sec": 4, "audio_cues": cues}]}


def test_audio_types_are_compiled_and_non_voice_never_carries_tts_text():
    cues = [
        {
            "kind": "voice",
            "line_type": "dialogue",
            "speaker": "hero",
            "spoken_text": "行こう。",
            "start_offset_sec": 0,
            "duration_sec": 1,
        },
        {
            "kind": "voice",
            "line_type": "inner_monologue",
            "speaker": "hero",
            "spoken_text": "不能回头",
            "start_offset_sec": 1,
            "duration_sec": 1,
        },
        {
            "kind": "voice",
            "line_type": "phone_broadcast",
            "speaker": "radio",
            "spoken_text": "警报",
            "start_offset_sec": 2,
            "duration_sec": 1,
        },
        {
            "kind": "foley",
            "asset_hint": "door",
            "source": "local:door.wav",
            "license": "own",
            "source_sha256": "a" * 64,
            "start_offset_sec": 0,
            "duration_sec": 1,
        },
        {
            "kind": "ambience",
            "asset_hint": "rain",
            "source": "https://example.test/rain.wav",
            "license": "cc0",
            "source_sha256": "b" * 64,
            "start_offset_sec": 0,
            "duration_sec": 4,
        },
        {
            "kind": "music",
            "asset_hint": "bed",
            "source": "local:bed.wav",
            "license": "own",
            "source_sha256": "c" * 64,
            "start_offset_sec": 0,
            "duration_sec": 4,
        },
        {"kind": "silence", "start_offset_sec": 3, "duration_sec": 0.5},
    ]
    timeline = compile_timeline(_spec(cues))
    assert {event["type"] for event in timeline["events"]} == {
        "dialogue",
        "inner_voice",
        "media_voice",
        "action_sfx",
        "ambience",
        "music",
        "silence",
    }
    assert all("text" not in event for event in timeline["events"] if event["type"] == "action_sfx")


def test_pending_noncommercial_sfx_cannot_enter_formal_timeline():
    with pytest.raises(AudioTimelineError, match="cannot enter a formal timeline"):
        validate_timeline(
            {
                "schema_version": 1,
                "kind": "audio-timeline",
                "events": [
                    {
                        "id": "pending-sfx",
                        "type": "action_sfx",
                        "shot_id": "s1",
                        "start_sec": 0,
                        "duration_sec": 1,
                        "gain": 1,
                        "pan": 0,
                        "source": "local:audio/candidates/sfx/pending/take.wav",
                        "license": "CC-BY-NC-4.0",
                        "source_sha256": "a" * 64,
                        "approval_status": "pending_human_review",
                        "production_eligible": False,
                    }
                ],
            }
        )


def test_approved_mmaudio_sfx_only_enters_noncommercial_internal_timeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "timeline-test-signing-key-12345")
    approved = tmp_path / "audio" / "candidates" / "sfx" / "approved-noncommercial"
    approved.mkdir(parents=True)
    source = approved / "take.wav"
    source.write_bytes(b"approved-audio")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt = approved / "take.receipt.json"
    record = sign_receipt(
        {
            "schema": "aifilm-sfx-candidate-v1",
            "asset_id": "mmaudio-sfx-test",
            "status": "approved_noncommercial",
            "production_eligible": False,
            "delivery_eligible_scopes": ["noncommercial_internal"],
            "approved_path": str(source.relative_to(tmp_path)),
            "sha256": source_hash,
            "license": "CC-BY-NC-4.0",
            "model": "hkchengrex/MMAudio-large-44k-v2",
            "checkpoint_fingerprint": "b" * 64,
            "node_job_id": "job-1",
            "human_review": {
                "reviewer": "dex",
                "heard_full": True,
                "sync_confirmed": True,
                "no_speech_confirmed": True,
                "no_music_confirmed": True,
                "artifact_free_confirmed": True,
            },
        }
    )
    write_json(receipt, record)
    cue = {
        "kind": "foley",
        "source": "local:audio/candidates/sfx/approved-noncommercial/take.wav",
        "license": "CC-BY-NC-4.0",
        "source_sha256": source_hash,
        "approval_status": "approved_noncommercial",
        "approval_receipt": ("local:audio/candidates/sfx/approved-noncommercial/take.receipt.json"),
        "production_eligible": False,
        "usage_scope": "noncommercial_internal",
        "model": "hkchengrex/MMAudio-large-44k-v2",
        "checkpoint_fingerprint": "b" * 64,
        "node_job_id": "job-1",
        "material": "wood",
        "start_offset_sec": 0,
        "duration_sec": 1,
    }
    internal = _spec([cue])
    internal["delivery_scope"] = "noncommercial_internal"
    with pytest.raises(AudioTimelineError, match="requires the film root"):
        compile_timeline(internal)
    timeline = compile_timeline(internal, root=tmp_path)
    assert timeline["delivery_scope"] == "noncommercial_internal"
    assert timeline["events"][0]["approval_status"] == "approved_noncommercial"

    forged = json.loads(json.dumps(internal))
    forged["shots"][0]["audio_cues"][0]["approval_receipt"] = (
        "local:audio/candidates/sfx/approved-noncommercial/missing.receipt.json"
    )
    with pytest.raises(AudioTimelineError, match="does not bind"):
        compile_timeline(forged, root=tmp_path)

    commercial = _spec([cue])
    commercial["delivery_scope"] = "commercial"
    with pytest.raises(AudioTimelineError, match="cannot enter a formal timeline"):
        compile_timeline(commercial, root=tmp_path)


@pytest.mark.parametrize(
    "license_id",
    (
        "CC-BY-NC-4.0",
        "CC BY-NC 4.0",
        "CC_BY_NC_4.0",
        "Creative Commons CC BY-NC 4.0",
    ),
)
def test_nc_license_family_cannot_enter_formal_timeline(license_id: str):
    with pytest.raises(AudioTimelineError, match="cannot enter a formal timeline"):
        validate_timeline(
            {
                "schema_version": 1,
                "kind": "audio-timeline",
                "events": [
                    {
                        "id": "nc-sfx",
                        "type": "action_sfx",
                        "shot_id": "s1",
                        "start_sec": 0,
                        "duration_sec": 1,
                        "gain": 1,
                        "pan": 0,
                        "source": "local:audio/imports/take.wav",
                        "license": license_id,
                        "source_sha256": "a" * 64,
                    }
                ],
            }
        )


def test_vocal_overlap_requires_explicit_policy():
    cues = [
        {
            "kind": "voice",
            "line_type": "dialogue",
            "speaker": "a",
            "spoken_text": "あ",
            "start_offset_sec": 0,
            "duration_sec": 2,
        },
        {
            "kind": "voice",
            "line_type": "dialogue",
            "speaker": "b",
            "spoken_text": "い",
            "start_offset_sec": 1,
            "duration_sec": 2,
        },
    ]
    with pytest.raises(AudioTimelineError, match="requires interrupt"):
        compile_timeline(_spec(cues))
    cues[1]["overlap_policy"] = "cross_talk"
    assert compile_timeline(_spec(cues))["events"][1]["overlap_policy"] == "cross_talk"


def test_style_rules_and_caption_bindings_are_event_bound():
    with pytest.raises(AudioTimelineError, match="forbids narration"):
        compile_timeline(
            _spec(
                [
                    {
                        "kind": "voice",
                        "line_type": "narration",
                        "speaker": "narrator",
                        "spoken_text": "旁白",
                        "start_offset_sec": 0,
                        "duration_sec": 1,
                    }
                ],
                mode="immersive_theatre",
            )
        )
    timeline = compile_timeline(
        _spec(
            [
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "speaker": "hero",
                    "spoken_text": "行こう",
                    "caption_text": "走吧",
                    "start_offset_sec": 0,
                    "duration_sec": 1,
                }
            ]
        )
    )
    bound = caption_bindings(timeline)
    assert bound[0]["audio_event_id"] == timeline["events"][0]["id"]
    assert bound[0]["caption_text"] == "走吧"


def test_stable_voice_profiles_respect_locks_and_language():
    first = assign_profiles(
        [{"speaker_id": "hero", "language": "ja"}, {"speaker_id": "narrator", "language": "zh"}]
    )
    again = assign_profiles([{"speaker_id": "hero", "language": "ja"}], first)
    assert first["hero"]["voice_id"] == again["hero"]["voice_id"]
    validate_event_language({"id": "x", "type": "dialogue"}, first["hero"])
    with pytest.raises(VoiceCastError, match="requires ja"):
        validate_event_language({"id": "x", "type": "dialogue"}, first["narrator"])


def test_asset_requires_hash_and_license_in_v1():
    with pytest.raises(AudioTimelineError, match="source_sha256"):
        compile_timeline(
            _spec(
                [
                    {
                        "kind": "sfx",
                        "asset_hint": "door",
                        "source": "local:door.wav",
                        "license": "own",
                        "start_offset_sec": 0,
                        "duration_sec": 1,
                    }
                ]
            )
        )


def test_performance_is_an_approval_gated_local_asset_type():
    cue = {
        "kind": "performance",
        "source": "local:audio/candidates/performance/approved/take.wav",
        "license": "original authorized performance",
        "source_sha256": "a" * 64,
        "approval_status": "approved",
        "approval_receipt": "local:audio/candidates/performance/approved/take.receipt.json",
        "character_id": "adult_a",
        "language": "nonverbal",
        "node_job_id": "job-42",
        "adult_confirmed": True,
        "source_authorization": "original",
        "take_seed": 42,
        "model_version": "higgs-audio-v2",
        "start_offset_sec": 0,
        "duration_sec": 1,
    }
    timeline = compile_timeline(_spec([cue]))
    assert timeline["events"][0]["type"] == "performance"
    cue["approval_status"] = "pending_human_review"
    with pytest.raises(AudioTimelineError, match="human approval"):
        compile_timeline(_spec([cue]))
    cue["approval_status"] = "approved"
    cue["take_seed"] = True
    with pytest.raises(AudioTimelineError, match="integer take_seed"):
        compile_timeline(_spec([cue]))
    cue["take_seed"] = 42
    cue["approval_receipt"] = "not-local"
    with pytest.raises(AudioTimelineError, match="approval_receipt"):
        compile_timeline(_spec([cue]))


def test_pending_ambient_candidate_cannot_enter_formal_timeline():
    cue = {
        "kind": "ambience",
        "source": "local:audio/candidates/ambient/pending/rain.wav",
        "license": "Stability AI Community License",
        "source_sha256": "a" * 64,
        "approval_status": "pending_human_review",
        "production_eligible": False,
        "start_offset_sec": 0,
        "duration_sec": 1,
    }

    with pytest.raises(AudioTimelineError, match="pending candidate"):
        compile_timeline(_spec([cue]))


def test_audio_timeline_schema_accepts_approved_performance_event() -> None:
    cue = {
        "kind": "performance",
        "source": "local:audio/candidates/performance/approved/take.wav",
        "license": "original authorized performance",
        "source_sha256": "a" * 64,
        "approval_status": "approved",
        "approval_receipt": "local:audio/candidates/performance/approved/take.receipt.json",
        "character_id": "adult_a",
        "language": "nonverbal",
        "node_job_id": "job-42",
        "adult_confirmed": True,
        "source_authorization": "original",
        "take_seed": 42,
        "model_version": "higgs-audio-v2",
        "start_offset_sec": 0,
        "duration_sec": 1,
    }
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "audio-timeline.schema.json"
    jsonschema.validate(compile_timeline(_spec([cue])), json.loads(schema_path.read_text()))


def test_performance_schemas_require_approval_provenance() -> None:
    schema_dir = Path(__file__).resolve().parent.parent / "schemas"
    timeline_schema = json.loads((schema_dir / "audio-timeline.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError, match="approval_receipt"):
        jsonschema.validate(
            {
                "schema_version": 1,
                "kind": "audio-timeline",
                "mode": "drama_radio",
                "duration_sec": 1,
                "events": [
                    {
                        "id": "p1",
                        "shot_id": "s1",
                        "type": "performance",
                        "start_sec": 0,
                        "duration_sec": 1,
                    }
                ],
            },
            timeline_schema,
        )
    film_schema = json.loads((schema_dir / "film-spec.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError, match="approval_receipt"):
        jsonschema.validate(
            {
                "schema_version": 2,
                "title": "schema-test",
                "shots": [
                    {
                        "id": "s1",
                        "nar": "旁白",
                        "dramatic_function": "reaction",
                        "dsl": {},
                        "audio_cues": [
                            {
                                "kind": "performance",
                                "start_offset_sec": 0,
                                "duration_sec": 1,
                            }
                        ],
                    }
                ],
            },
            film_schema,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("adult_confirmed", False, "adult_confirmed"),
        ("source_authorization", "unknown", "authorization"),
        ("model_version", "", "model_version"),
        ("source_sha256", "not-a-hash", "source_sha256"),
    ],
)
def test_performance_contract_rejects_missing_provenance(
    field: str, value: object, message: str
) -> None:
    cue = {
        "kind": "performance",
        "source": "local:audio/candidates/performance/approved/take.wav",
        "license": "original authorized performance",
        "source_sha256": "a" * 64,
        "approval_status": "approved",
        "approval_receipt": "local:audio/candidates/performance/approved/take.receipt.json",
        "character_id": "adult_a",
        "language": "nonverbal",
        "node_job_id": "job-42",
        "adult_confirmed": True,
        "source_authorization": "original",
        "take_seed": 42,
        "model_version": "higgs-audio-v2",
        "start_offset_sec": 0,
        "duration_sec": 1,
    }
    cue[field] = value
    with pytest.raises(AudioTimelineError, match=message):
        compile_timeline(_spec([cue]))


def test_mix_plan_has_inner_voice_filter_event_pan_fades_and_all_vocal_ducking():
    timeline = compile_timeline(
        _spec(
            [
                {
                    "kind": "voice",
                    "line_type": "inner_monologue",
                    "speaker": "hero",
                    "spoken_text": "不能回头",
                    "start_offset_sec": 1,
                    "duration_sec": 2,
                    "pan": -0.5,
                    "fade_in_sec": 0.2,
                    "fade_out_sec": 0.3,
                },
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "speaker": "heroine",
                    "spoken_text": "快走",
                    "start_offset_sec": 3,
                    "duration_sec": 1,
                },
            ]
        )
    )
    plan = build_mix_execution_plan(timeline)
    first = plan["lanes"][0]
    assert plan["sample_rate"] == 48000
    assert "highpass=f=250,lowpass=f=3200" in first["filters"]
    assert any(item.startswith("pan=stereo") for item in first["filters"])
    assert plan["ducking"]["trigger_event_ids"] == [event["id"] for event in timeline["events"]]


def test_stable_audio_license_cannot_enter_formal_timeline_after_metadata_stripping():
    with pytest.raises(AudioTimelineError, match="candidate"):
        compile_timeline(
            _spec(
                [
                    {
                        "kind": "ambience",
                        "source": "local:assets/rain.wav",
                        "source_sha256": "a" * 64,
                        "license": "Stability AI Community License",
                        "start_offset_sec": 0,
                        "duration_sec": 1,
                    }
                ]
            )
        )


def test_rebase_keeps_cue_offset_when_rendered_shot_start_changes():
    timeline = compile_timeline(
        _spec(
            [
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "speaker": "hero",
                    "spoken_text": "行こう",
                    "start_offset_sec": 1.2,
                    "duration_sec": 1,
                }
            ]
        )
    )

    rebased = rebase_to_rendered_shots(timeline, {"s1": 4.5})

    assert rebased["events"][0]["start_sec"] == 5.7


def test_rebase_rejects_tampered_stored_event_that_exceeds_rendered_shot():
    timeline = compile_timeline(
        _spec([{"kind": "silence", "start_offset_sec": 3.9, "duration_sec": 0.05}])
    )
    timeline["events"][0]["duration_sec"] = 0.2
    with pytest.raises(AudioTimelineError, match="exceeds rendered shot duration"):
        rebase_to_rendered_shots(timeline, {"s1": 0.0}, shot_durations={"s1": 4.0})


def test_silence_is_a_bed_control_and_cannot_overlap_vocal_or_escape_shot():
    timeline = compile_timeline(
        _spec(
            [
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "speaker": "hero",
                    "spoken_text": "先别出声",
                    "start_offset_sec": 0,
                    "duration_sec": 1,
                },
                {
                    "kind": "silence",
                    "start_offset_sec": 2,
                    "duration_sec": 0.5,
                    "silence_scope": "bed",
                },
            ]
        )
    )
    plan = build_mix_execution_plan(timeline)
    assert plan["silence_windows"] == [
        {
            "audio_event_id": timeline["events"][1]["id"],
            "start_sec": 2.0,
            "end_sec": 2.5,
            "scope": "bed",
        }
    ]
    overlapping = _spec(
        [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "别动",
                "start_offset_sec": 0,
                "duration_sec": 1,
            },
            {"kind": "silence", "start_offset_sec": 0.5, "duration_sec": 0.5},
        ]
    )
    with pytest.raises(AudioTimelineError, match="overlaps vocal"):
        compile_timeline(overlapping)
    escaped = _spec([{"kind": "silence", "start_offset_sec": 3.9, "duration_sec": 0.2}])
    with pytest.raises(AudioTimelineError, match="exceeds shot"):
        compile_timeline(escaped)


def test_audio_plan_writes_timeline_and_deterministic_voice_cast(tmp_path: Path):
    spec = _spec(
        [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "行こう",
                "start_offset_sec": 0,
                "duration_sec": 1,
            }
        ]
    )
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    report = build_audio_plan(
        tmp_path, compile_timeline=True, write_timeline=True, write_voice_cast=True
    )
    assert report["audio_timeline"]["event_count"] == 1
    assert (tmp_path / "audio" / "audio-timeline.json").is_file()
    profile = report["voice_cast"]["profiles"]["hero"]
    assert profile["language"] == "ja"
    assert profile["voice_id"].startswith("ja-JP-")
