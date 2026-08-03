from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_contract import validate_dialogue_contract  # noqa: E402
from dialogue_contracts import summarize_dialogue_contracts  # noqa: E402


def _contract() -> dict:
    return {
        "shot_id": "shot01",
        "shot_window": {"start_sec": 10.0, "end_sec": 12.0},
        "lines": [
            {
                "line_id": "line-1",
                "text_sha256": "b" * 64,
                "delivery": "quiet warning",
                "window": {"start_sec": 10.2, "end_sec": 11.4},
                "audio_origin": "native",
                "lipsync_required": True,
                "lipsync_evidence": {
                    "method": "generated_native_audio",
                    "artifact_sha256": "c" * 64,
                },
            }
        ],
    }


def test_native_dialogue_with_true_lipsync_evidence_is_valid() -> None:
    assert validate_dialogue_contract(_contract())["ok"]


def test_silent_i2v_with_post_vo_is_not_native_audio_or_true_lipsync() -> None:
    contract = _contract()
    line = contract["lines"][0]
    line["audio_origin"] = "post_vo"
    line["source_video_audio"] = "silent"
    line["lipsync_evidence"] = {
        "method": "timed_post_vo",
        "artifact_sha256": "d" * 64,
    }

    report = validate_dialogue_contract(contract)

    codes = {issue["code"] for issue in report["errors"]}
    assert "POST_VO_NOT_NATIVE_AUDIO" in codes
    assert "TRUE_LIPSYNC_EVIDENCE_MISSING" in codes


def test_dialogue_must_remain_inside_shot_window() -> None:
    contract = _contract()
    contract["lines"][0]["window"]["end_sec"] = 12.1

    report = validate_dialogue_contract(contract)

    assert "DIALOGUE_OUTSIDE_SHOT_WINDOW" in {issue["code"] for issue in report["errors"]}


def test_shared_summary_preserves_shot_id_and_contract_count() -> None:
    bad = _contract()
    bad["lines"][0]["window"]["end_sec"] = 12.1

    report = summarize_dialogue_contracts(
        [
            {"id": "s001", "dialogue_contracts": [_contract()]},
            {"id": "s002", "dialogue_contracts": [bad]},
        ]
    )

    assert report["contracts_validated"] == 2
    assert report["error_count"] == 1
    assert report["errors"][0]["shot_id"] == "s002"


def test_shared_summary_rejects_non_object_contracts() -> None:
    report = summarize_dialogue_contracts([{"id": "s001", "dialogue_contracts": [None]}])

    assert report["ok"] is False
    assert report["codes"] == ["DIALOGUE_CONTRACT_INVALID"]
    assert report["errors"][0]["shot_id"] == "s001"


# ─── Gate path tests (write-spec strict + preflight) ─────────────────────


def _dc_shot(sid="shot01", *, contracts=None):
    """Minimal shot for write-spec validation, optionally carrying dialogue_contracts."""
    sh = {
        "id": sid,
        "dramatic_function": "approach",
        "nar": f"旁白{sid}。",
        "dsl": {
            "subject": "woman",
            "cast": ["heroine"],
            "camera": {"shot_size": "medium"},
            "motion": "idle",
        },
    }
    if contracts is not None:
        sh["dialogue_contracts"] = contracts
    return sh


def _dc_spec(shots):
    return {
        "schema_version": 1,
        "title": "dc-test",
        "vo_mode": "storyteller",
        "dialogue_spoken_lang": "zh",
        "narration_spoken_lang": "zh",
        "aspect": "9:16",
        "director_intent": {
            "logline": "Test dialogue contracts.",
            "tone": "neutral",
            "emotional_arc": ["a", "b", "c"],
        },
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": [{"shots": shots}],
    }


def _good_contract():
    return {
        "shot_id": "shot01",
        "shot_window": {"start_sec": 10.0, "end_sec": 12.0},
        "lines": [
            {
                "line_id": "line-1",
                "text_sha256": "b" * 64,
                "delivery": "quiet warning",
                "window": {"start_sec": 10.2, "end_sec": 11.4},
                "audio_origin": "native",
                "lipsync_required": True,
                "lipsync_evidence": {
                    "method": "generated_native_audio",
                    "artifact_sha256": "c" * 64,
                },
            }
        ],
    }


def _bad_contract():
    """Post-VO on silent I2V with no real lipsync evidence."""
    c = _good_contract()
    c["lines"][0]["audio_origin"] = "post_vo"
    c["lines"][0]["source_video_audio"] = "silent"
    c["lines"][0]["lipsync_evidence"] = {"method": "timed_post_vo", "artifact_sha256": "d" * 64}
    return c


class TestWriteSpecDialogueContractGate:
    """dialogue_contract_strict=True → FilmSpecError when contract violations detected."""

    def test_strict_raises_on_bad_contract(self):
        from film_spec import FilmSpecError, validate_film_spec

        shots = [_dc_shot(contracts=[_bad_contract()])]
        spec = _dc_spec(shots)
        spec["dialogue_contract_strict"] = True
        with pytest.raises(FilmSpecError, match="dialogue_contract_strict"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_non_strict_no_raise_on_bad_contract(self):
        from film_spec import validate_film_spec

        shots = [_dc_shot(contracts=[_bad_contract()])]
        spec = _dc_spec(shots)
        validate_film_spec(spec, assign_missing_ids=False)
        pcr = spec.get("_dialogue_contracts") or {}
        assert not pcr.get("ok", True)
        assert pcr.get("error_count", 0) > 0

    def test_strict_passes_on_good_contract(self):
        from film_spec import validate_film_spec

        shots = [_dc_shot(contracts=[_good_contract()])]
        spec = _dc_spec(shots)
        spec["dialogue_contract_strict"] = True
        validate_film_spec(spec, assign_missing_ids=False)
        pcr = spec.get("_dialogue_contracts") or {}
        assert pcr.get("ok") is True

    def test_no_contracts_no_issue(self):
        from film_spec import validate_film_spec

        shots = [_dc_shot()]
        spec = _dc_spec(shots)
        spec["dialogue_contract_strict"] = True
        validate_film_spec(spec, assign_missing_ids=False)
        pcr = spec.get("_dialogue_contracts") or {}
        assert pcr.get("ok") is True
        assert pcr.get("contracts_validated") == 0

    def test_strict_rejects_non_object_contract(self):
        from film_spec import FilmSpecError, validate_film_spec

        spec = _dc_spec([_dc_shot(contracts=[None])])
        spec["dialogue_contract_strict"] = True
        with pytest.raises(FilmSpecError, match="dialogue_contract_strict"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_dialogue_drama_rejects_unbound_or_implicit_voice(self):
        from film_spec import FilmSpecError, validate_film_spec

        # v2.34: scene-level dialogue-first gate rejects scenes without any dialogue
        # cue first; give the scene a second, fully legal talking shot and put the
        # bad shot in beat b1 with matching reaction coverage so neither the scene
        # gate nor the beat-coverage gate can fire before the audio_cues check.
        talking = {
            **_dc_shot("talk00"),
            "screen_mode": "on_camera",
            "speaker": "hero",
            "dialogue_line_id": "ln_talk00",
            "performance_state_id": "st_talk00",
            "lipsync_required": True,
            "speaker_on_camera": True,
            "lipsync": True,
            "beat_id": "b0",
            "caption_text": "别走。",
            "nar": "别走。",
            "duration_sec": 8,
            "audio_cues": [
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "language": "zh",
                    "speaker": "hero",
                    "spoken_text": "别走。",
                    "duration_sec": 8,
                }
            ],
            "performance_state": {"head_angle": "front"},
            "dsl": {
                **_dc_shot("talk00")["dsl"],
                "camera": {"shot_size": "close-up"},
            },
        }
        cover_b0 = {
            **_dc_shot("cover_b0"),
            "screen_mode": "reaction",
            "beat_id": "b0",
            "duration_sec": 2,
            # keep nar short enough that est_vo_sec (≈len/6.2) ≤ 2.0 + slack 0.5
            "nar": "静场。",
            "audio_cues": [{"kind": "silence", "start_offset_sec": 0, "duration_sec": 2}],
        }
        bad = _dc_shot()
        bad.pop("nar")
        bad["screen_mode"] = "on_camera"
        spec = _dc_spec([talking, cover_b0, bad])
        spec["vo_mode"] = "dialogue_drama"
        spec["dialogue_spoken_lang"] = "ja"
        spec["narration_spoken_lang"] = "zh"
        with pytest.raises(FilmSpecError, match="audio_cues"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_dialogue_drama_narration_budget_is_optional_but_enforceable(self):
        from film_spec import FilmSpecError, validate_film_spec

        spec = _dc_spec(
            [
                {
                    **_dc_shot("talk01"),
                    "screen_mode": "on_camera",
                    "dialogue_line_id": "dlg_01",
                    "speaker": "hero",
                    "speaker_on_camera": True,
                    "lipsync": True,
                    "lipsync_required": True,
                    "performance_state_id": "hero-sc01-talk01",
                    "performance_state": {"head_angle": "three-quarter"},
                    "dsl": {
                        **_dc_shot("talk01")["dsl"],
                        "camera": {"shot_size": "medium close-up"},
                    },
                    "audio_cues": [
                        {
                            "kind": "voice",
                            "line_type": "dialogue",
                            "speaker": "hero",
                            "spoken_text": "别走。",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        }
                    ],
                },
                {
                    **_dc_shot("bridge01"),
                    "screen_mode": "action_cover",
                    "narration_reason": "time jump",
                    "audio_cues": [
                        {
                            "kind": "voice",
                            "line_type": "narration",
                            "speaker": "narrator",
                            "spoken_text": "三天后。",
                            "start_offset_sec": 0,
                            "duration_sec": 3,
                        }
                    ],
                },
                {
                    **_dc_shot("cover01"),
                    "screen_mode": "action_cover",
                    "beat_id": "dlg_01",
                    "audio_cues": [{"kind": "silence", "start_offset_sec": 0, "duration_sec": 1}],
                },
            ]
        )
        spec["vo_mode"] = "dialogue_drama"
        spec["dialogue_spoken_lang"] = "ja"
        spec["narration_spoken_lang"] = "zh"
        spec["scenes"][0]["shots"][0].update(
            {
                "dialogue": "别走。",
                "caption_text": "别走。",
                "translation_status": "ready",
                "beat_id": "dlg_01",
            }
        )
        spec["scenes"][0]["shots"][0]["audio_cues"][0]["spoken_text"] = "别走。"
        spec["scenes"][0]["shots"][0]["audio_cues"][0]["language"] = "zh"
        for shot in spec["scenes"][0]["shots"]:
            shot.pop("nar", None)
        with pytest.raises(FilmSpecError, match="narration budget"):
            validate_film_spec(spec, assign_missing_ids=False)


class TestPreflightDialogueContractGate:
    """preflight reports dialogue_contract_violation soft (default) / hard (strict)."""

    def _make_root(self, shots, *, strict=False):
        tmp = tempfile.mkdtemp(prefix="aifilm_dc_test_")
        root = Path(tmp)
        spec = _dc_spec(shots)
        if strict:
            spec["dialogue_contract_strict"] = True
        (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return root

    def test_preflight_soft_on_bad_contract_default(self):
        import preflight

        shots = [_dc_shot(contracts=[_bad_contract()])]
        root = self._make_root(shots, strict=False)
        rep = preflight.run_preflight(root)
        soft_codes = [i["code"] for i in rep["soft"]]
        assert "dialogue_contract_violation" in soft_codes

    def test_preflight_hard_on_bad_contract_strict(self):
        import preflight

        shots = [_dc_shot(contracts=[_bad_contract()])]
        root = self._make_root(shots, strict=True)
        rep = preflight.run_preflight(root)
        hard_codes = [i["code"] for i in rep["hard"]]
        assert "dialogue_contract_violation" in hard_codes
        assert not rep["hard_ok"]

    def test_preflight_clean_no_issue(self):
        import preflight

        shots = [_dc_shot(contracts=[_good_contract()])]
        root = self._make_root(shots, strict=True)
        rep = preflight.run_preflight(root)
        all_codes = [i["code"] for i in rep["hard"]] + [i["code"] for i in rep["soft"]]
        assert "dialogue_contract_violation" not in all_codes

    def test_preflight_hard_on_non_object_contract_strict(self):
        import preflight

        root = self._make_root([_dc_shot(contracts=[None])], strict=True)
        rep = preflight.run_preflight(root)
        assert "dialogue_contract_violation" in [item["code"] for item in rep["hard"]]
